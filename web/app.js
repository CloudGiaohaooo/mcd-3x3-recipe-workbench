/* 麦门 3×3 配方工作台 —— 前端逻辑（无依赖，原生 JS） */
"use strict";

const $ = (sel) => document.querySelector(sel);

const DOMAIN_COLOR = {
  主食: "#DA291C", 小食: "#F5A623", 饮品: "#2E86DE",
  甜品: "#E84393", 券: "#8E44AD", 套餐: "#1F7A3D",
};
const DOMAIN_ICON = {
  主食: "🍔", 小食: "🍟", 饮品: "🥤", 甜品: "🍦", 券: "🎟️", 套餐: "🍱",
};

const state = {
  menu: {},        // name -> item
  order: [],
  mode: "compose",
  grid: {},        // "r,c" -> name
  selected: null,
  cards: [],
  cardIdx: 0,
};

// 内置预设：?preset=巨无霸薯条可乐 直接摆好并出结果（也用于分享链接 / 截图）
const PRESETS = {
  "巨无霸薯条可乐": [["巨无霸", "2,2"], ["薯条", "2,1"], ["可乐", "3,2"]],
  "可乐主推反转": [["可乐", "2,2"], ["薯条", "2,1"], ["巨无霸", "3,2"]],
  "麦旋风下午茶": [["麦旋风", "2,2"], ["可乐", "2,1"], ["苹果派", "3,2"]],
  "满减凑单": [["满30减5券", "2,2"], ["巨无霸", "2,1"], ["可乐", "3,2"]],
};

function domColor(d) { return DOMAIN_COLOR[d] || "#8A8178"; }

// 元素图标：优先用 Q 版像素图（web/sprites/<id>.png），加载失败回退 emoji
function spriteURL(it) { return it && it.id ? "sprites/" + it.id + ".png" : null; }

function emEl(it) {
  const url = spriteURL(it);
  if (!url) {
    const s = document.createElement("span");
    s.className = "em";
    s.textContent = it.emoji || "🍴";
    return s;
  }
  const img = document.createElement("img");
  img.className = "em sprite";
  img.src = url;
  img.alt = it.name;
  img.onerror = () => {
    const s = document.createElement("span");
    s.className = "em";
    s.textContent = it.emoji || "🍴";
    img.replaceWith(s);
  };
  return img;
}

function emHTML(it) {
  const url = spriteURL(it);
  const fallback = escapeHtml(it.emoji || "🍴");
  if (!url) return `<span class="em">${fallback}</span>`;
  return `<img class="em sprite" src="${url}" alt="${escapeHtml(it.name)}" onerror="this.outerHTML='<span class=\'em\'>${fallback}</span>'">`;
}

async function api(path, body) {
  const opt = body ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  } : { method: "GET" };
  const r = await fetch(path, opt);
  return r.json();
}

/* ---------- 初始化 ---------- */
async function init() {
  const menu = await api("/api/menu");
  if (!menu.ok) { alert(menu.error); return; }
  state.order = menu.order;
  state.menu = {};
  menu.items.forEach((it) => { state.menu[it.name] = it; });
  $("#srcNote").textContent = menu.live ? "MCP 实时价" : "离线示例价";
  if (menu.live) $("#liveBtn").classList.add("on");
  renderPalette(menu.groups);
  renderGrid();
  bind();
  handlePreset();
}

/* ?preset=场景名 或 ?preset=decompose:单品名 —— 自动摆好并出结果 */
async function handlePreset() {
  const q = new URLSearchParams(location.search).get("preset");
  if (!q) return;
  if (q.startsWith("decompose:")) {
    const name = q.slice("decompose:".length);
    if (state.menu[name]) { setMode("decompose"); decompose(name); }
    return;
  }
  const scenario = PRESETS[q];
  if (!scenario) return;
  scenario.forEach(([name, pos]) => { state.grid[pos] = name; });
  refreshGrid();
  await compose();
}

/* ---------- 渲染物品库 ---------- */
function renderPalette(groups) {
  const box = $("#paletteGroups");
  box.innerHTML = "";
  state.order.forEach((d) => {
    const items = groups[d] || [];
    if (!items.length) return;
    const cat = document.createElement("div");
    cat.className = "cat";
    const title = document.createElement("div");
    title.className = "cat-title";
    title.textContent = DOMAIN_ICON[d] + " " + d;
    cat.appendChild(title);
    items.forEach((it) => cat.appendChild(chipEl(it)));
    box.appendChild(cat);
  });
}

function chipEl(it) {
  const c = document.createElement("div");
  c.className = "chip";
  c.draggable = true;
  c.dataset.name = it.name;

  const em = emEl(it);

  const meta = document.createElement("div");
  meta.className = "meta";
  const nm = document.createElement("div");
  nm.className = "nm";
  nm.textContent = it.name;
  const pr = document.createElement("div");
  pr.className = "pr";
  pr.textContent = it.domain === "券" ? "优惠券" : ("¥" + it.price + (it.calories ? " · " + it.calories + " kcal" : ""));
  meta.appendChild(nm); meta.appendChild(pr);

  const tag = document.createElement("span");
  tag.className = "tag";
  tag.textContent = it.domain;
  tag.style.background = domColor(it.domain);

  c.appendChild(em); c.appendChild(meta); c.appendChild(tag);

  c.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/plain", it.name);
    e.dataTransfer.effectAllowed = "copy";
  });
  c.addEventListener("click", () => onChipClick(it.name));
  return c;
}

/* ---------- 渲染九宫格 ---------- */
function renderGrid() {
  const grid = $("#grid");
  grid.innerHTML = "";
  for (let r = 1; r <= 3; r++) {
    for (let c = 1; c <= 3; c++) {
      const pos = `${r},${c}`;
      grid.appendChild(cellEl(pos));
    }
  }
}

function cellEl(pos) {
  const cell = document.createElement("div");
  cell.className = "cell";
  cell.dataset.pos = pos;
  if (pos === "2,2") cell.dataset.center = "1";

  const badge = document.createElement("span");
  badge.className = "role-badge";
  badge.textContent = "主推";
  cell.appendChild(badge);

  cell.addEventListener("dragover", (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    cell.classList.add("dragover");
  });
  cell.addEventListener("dragleave", () => cell.classList.remove("dragover"));
  cell.addEventListener("drop", (e) => {
    e.preventDefault();
    cell.classList.remove("dragover");
    const name = e.dataTransfer.getData("text/plain");
    if (name && state.menu[name]) place(name, pos);
  });
  cell.addEventListener("click", () => onCellClick(pos));
  paintCell(cell, pos);
  return cell;
}

function paintCell(cell, pos) {
  const name = state.grid[pos];
  // 清掉除 role-badge 外的内容
  [...cell.querySelectorAll(".em,.nm,.rm,.drop-hint")].forEach((n) => n.remove());
  if (!name) {
    cell.classList.remove("filled");
    const hint = document.createElement("span");
    hint.className = "drop-hint";
    hint.textContent = pos === "2,2" ? "放主推" : "放单品";
    cell.appendChild(hint);
    return;
  }
  const it = state.menu[name];
  cell.classList.add("filled");
  const em = emEl(it);
  const nm = document.createElement("span");
  nm.className = "nm";
  nm.textContent = name;
  const rm = document.createElement("button");
  rm.className = "rm";
  rm.textContent = "×";
  rm.title = "移除";
  rm.addEventListener("click", (e) => { e.stopPropagation(); removeItem(pos); });
  cell.appendChild(em); cell.appendChild(nm); cell.appendChild(rm);
}

/* ---------- 交互 ---------- */
function place(name, pos) {
  // 已占用则移除旧的
  Object.keys(state.grid).forEach((p) => {
    if (state.grid[p] === name && p !== pos) delete state.grid[p];
  });
  state.grid[pos] = name;
  refreshGrid();
  state.selected = null;
  refreshSelection();
}

function removeItem(pos) {
  delete state.grid[pos];
  refreshGrid();
}

function clearGrid() {
  state.grid = {};
  state.cards = [];
  refreshGrid();
  $("#resultBody").innerHTML = emptyHTML();
  $("#resultCount").textContent = "";
}

function refreshGrid() {
  document.querySelectorAll(".cell").forEach((cell) => paintCell(cell, cell.dataset.pos));
}

function refreshSelection() {
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.classList.toggle("selected", chip.dataset.name === state.selected);
  });
  const hint = $("#boardHint");
  if (state.mode === "decompose") {
    hint.textContent = "点任意单品看它的原料、卖点与营养";
  } else if (state.selected) {
    hint.textContent = "已选中「" + state.selected + "」，点一个空格放下";
  } else {
    hint.textContent = "把单品拖进九宫格 —— 正中间那格是「主推」";
  }
}

function onChipClick(name) {
  if (state.mode === "decompose") { decompose(name); return; }
  state.selected = state.selected === name ? null : name;
  refreshSelection();
}

function onCellClick(pos) {
  const name = state.grid[pos];
  if (state.mode === "decompose") {
    if (name) decompose(name);
    else if (state.selected) decompose(state.selected);
    return;
  }
  if (state.selected) { place(state.selected, pos); return; }
  if (name) removeItem(pos);
}

/* ---------- 合成 / 分解 ---------- */
async function compose() {
  const items = Object.keys(state.grid).map((pos) => ({ name: state.grid[pos], position: pos }));
  if (items.length < 2) {
    $("#resultBody").innerHTML = warnHTML("至少放 2 个单品进九宫格再合成。");
    return;
  }
  const data = await api("/api/compose", { items });
  if (!data.ok) { $("#resultBody").innerHTML = warnHTML(data.error); return; }
  renderCompose(data);
}

async function decompose(name) {
  const data = await api("/api/decompose", { name });
  if (!data.ok) { $("#resultBody").innerHTML = warnHTML(data.error); return; }
  renderDecompose(data);
}

async function liveToggle() {
  const btn = $("#liveBtn");
  const data = await api("/api/live", {});
  if (!data.ok) {
    alert(data.error + "\n\n设置后重新运行：\n  set MCD_MCP_TOKEN=<你的Token>\n再重启 web.py 点此按钮。");
    return;
  }
  btn.classList.add("on");
  $("#srcNote").textContent = "MCP 实时价";
  init(); // 重新拉菜单显示真实价
  $("#resultBody").innerHTML =
    "<div class='warn' style='background:#E7F5EC;border-color:#BFE3CD;color:#1F7A3D'>✓ 已接入麦当劳 MCP 实时数据<br>" +
    "<span style='font-weight:400'>" + escapeHtml(data.store || "") + "</span></div>";
}

/* ---------- 渲染结果 ---------- */
function renderCompose(data) {
  state.cards = data.cards || [];
  state.cardIdx = 0;
  $("#srcNote").textContent = data.live ? "MCP 实时价" : "离线示例价";
  if (!state.cards.length) {
    $("#resultBody").innerHTML = warnHTML(data.message || "这组没合成出合格配方，换一组或减一个单品。");
    $("#resultCount").textContent = "";
    return;
  }
  $("#resultCount").textContent = "共 " + state.cards.length + " 张，第 1 张最优";
  drawCard(0);
}

function drawCard(idx) {
  const card = state.cards[idx];
  const body = $("#resultBody");
  const total = state.cards.length;

  const sd = card.score_detail || {};
  const bars = [
    ["需求", sd.need], ["惊喜", sd.surprise], ["替代", sd.replacement],
    ["可做", sd.doable_tonight], ["说明书", sd.manual_complete], ["位置", sd.position_evidence],
  ].map(([k, v]) =>
    `<div class="bar"><span class="k">${k}</span><div class="track"><div class="fill" style="width:${(v || 0) * 100 / 20}%"></div></div></div>`
  ).join("");

  const elements = (card.参与元素 || []).map((n) => {
    const it = state.menu[n];
    return `<span class="elem">${it ? emHTML(it) : "🍴"} ${n}</span>`;
  }).join("");

  const excluded = (card.剔除清单 || []);
  const exLine = excluded.length
    ? excluded.map((e) => `<span class="mini-tag fail">剔除 ${e.item}：${e.reason}</span>`).join("")
    : `<span class="mini-tag ok">无剔除</span>`;

  const steps = (card.说明书 || []).map((s) => `<li>${escapeHtml(s)}</li>`).join("");
  const fails = (card.失败点 || []).map((f) => `<span class="mini-tag fail">${escapeHtml(f)}</span>`).join("");

  body.innerHTML = `
    <div class="card">
      <div class="card-head">
        <div class="card-finding">${escapeHtml(card["一句发现"] || "")}</div>
        <div class="score-badge"><div class="n">${card.score}</div><div class="l">分 / 100</div></div>
      </div>
      <div class="card-what">${escapeHtml(card["这是什么"] || "")}</div>

      <div class="sec"><div class="sec-title">参与元素</div><div class="elem-row">${elements}</div></div>
      <div class="sec"><div class="sec-title">说明书</div><ol class="steps">${steps}</ol></div>
      <div class="sec"><div class="sec-title">替代了什么</div><div class="muted-line">${escapeHtml(card["替代了什么"] || "")}</div></div>
      <div class="sec"><div class="sec-title">剔除清单</div><div class="chipline">${exLine}</div></div>
      <div class="sec"><div class="sec-title">失败点</div><div class="chipline">${fails}</div></div>
      <div class="sec"><div class="sec-title">最小验证</div><div class="muted-line">${escapeHtml(card["最小验证"] || "")}</div></div>
      <div class="sec"><div class="sec-title">位置依据</div><div class="muted-line">${escapeHtml(card["位置依据"] || "")}</div></div>
      <div class="sec"><div class="sec-title">打分</div><div class="score-bars">${bars}</div></div>

      <div class="card-actions">
        ${idx < total - 1 ? `<button class="btn ghost" onclick="drawCard(${idx + 1})">换一张（${idx + 2}/${total}）</button>` : ""}
        <button class="btn ghost" onclick="compose()">重新生成</button>
      </div>
    </div>`;
  $("#resultCount").textContent = "第 " + (idx + 1) + " / " + total + " 张";
}

function renderDecompose(data) {
  const p = data.profile;
  const dec = data.decomposition || {};
  $("#srcNote").textContent = data.live ? "MCP 实时价" : "离线示例价";
  $("#resultCount").textContent = "";

  const ing = (p.ingredients || []).map((x) => `<span class="ing">${escapeHtml(x)}</span>`).join("") || "—";
  const coups = (p.coupons || []).map((c) => `<span class="mini-tag ok">${escapeHtml(c.name)}</span>`).join("") || "暂无可用券";
  const comps = (p.components || []).map((c) =>
    `<span class="elem">${emHTML(c)} ${c.name} <span style="color:var(--muted)">¥${c.price}</span></span>`
  ).join("") || "";

  const compSec = p.components && p.components.length
    ? `<div class="sec"><div class="sec-title">套餐构成</div><div class="elem-row">${comps}</div></div>` : "";

  const paths = (dec.paths || []).map((pt) => `
    <div class="path">
      <div class="ext">${escapeHtml(pt.extract)}</div>
      <div class="how">怎么拆：${escapeHtml((pt.how || []).join(" → "))}</div>
      <div class="risks">风险：${escapeHtml((pt.risks || []).join("、"))} · 验证：${escapeHtml(pt.min_validation || "")}</div>
    </div>`).join("");

  const danger = (dec.dangerous_items_blocked || []).length
    ? `<div class="warn">⚠ 危险项拦截，不展开步骤：${escapeHtml(dec.dangerous_items_blocked.join("、"))}</div>` : "";

  $("#resultBody").innerHTML = `
    <div class="profile-head">
      ${emHTML(p)}
      <div>
        <h3>${escapeHtml(p.name)}</h3>
        <div class="tagline">${escapeHtml(p.tagline || p.description || "")}</div>
      </div>
    </div>
    ${danger}
    <div class="sec">
      <div class="sec-title">产品档案</div>
      <div class="kv">
        <div class="stat"><div class="v">¥${p.price}</div><div class="k">${data.live ? "实时价" : "示例价"}</div></div>
        <div class="stat"><div class="v">${p.calories} kcal</div><div class="k">${data.live ? "实时热量" : "示例热量"}</div></div>
        <div class="stat"><div class="v">${escapeHtml(p.domain)}</div><div class="k">类别</div></div>
      </div>
    </div>
    <div class="sec"><div class="sec-title">原料 / 配料</div><div class="ing-row">${ing}</div></div>
    <div class="sec"><div class="sec-title">可用优惠</div><div class="chipline">${coups}</div></div>
    ${compSec}
    <div class="sec"><div class="sec-title">分解 / 搭配路径</div>${paths || '<div class="muted-line">无</div>'}</div>`;
}

/* ---------- 工具 ---------- */
function emptyHTML() {
  return `<div class="empty"><img class="empty-emoji" src="sprites/fries.png" alt="薯条">
    <p>左边选好单品放进九宫格，<br>点「生成配方」看结果。</p>
    <p class="empty-tip">点「分解 / 单品详情」后，直接点任意单品看它的原料、卖点与营养。</p></div>`;
}

function warnHTML(msg) {
  return `<div class="warn">${escapeHtml(msg)}</div>`;
}

function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ---------- 事件绑定 ---------- */
function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll(".mode-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.mode === mode);
  });
  $("#goBtn").style.display = mode === "compose" ? "" : "none";
  refreshSelection();
}

function bind() {
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => setMode(btn.dataset.mode));
  });
  $("#goBtn").addEventListener("click", compose);
  $("#clearBtn").addEventListener("click", clearGrid);
  $("#liveBtn").addEventListener("click", liveToggle);
}

window.drawCard = drawCard; // 供按钮内联 onclick 使用
init();
