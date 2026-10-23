"""规则生成器的合成引擎（麦当劳版，位置驱动）。

核心思路：不是「从单品拼套餐」，而是「单品类别 × 格子角色」。
- 中心格单品 = 主推（main），其它单品 = 搭配。
- 三件套 = 主食 + 小食 + 饮品；双件套 = 主食+饮品 / 主食+小食；下午茶 = 饮品+甜品 / 小食+甜品。
- 券单独处理：满减凑单 / 单品券直减。
- 位置依据按真实坐标动态生成，不在 2,2 绝不写「在中心」。

build_food(main, aux, items) 生成 main 为「主推」的候选 spec；
match_all(items, roles, positions, mode) 枚举子集 × main 后去重汇总。
"""
from __future__ import annotations

from itertools import combinations
from typing import Dict, List

from .catalog import CATALOG, COUPONS
from .schema import Item

FOOD_DOMAINS = ("主食", "小食", "饮品", "甜品")

# 目录套餐按「构成单品集合」反查，合成时取真实套餐价（不虚构 85 折）
_MEAL_BY_COMBO = {
    frozenset(m.constraints): m
    for m in CATALOG.values()
    if m.type == "meal" and m.constraints
}


def _has(item: Item, attr: str) -> bool:
    return attr in item.attributes


def _price_of(items: Dict[str, Item], names: List[str]) -> float:
    return round(sum(items[n].price for n in names), 1)


def _cal_of(items: Dict[str, Item], names: List[str]) -> int:
    return sum(items[n].calories for n in names)


def _combo_of(items: Dict[str, Item], names: List[str]):
    """真实组合价：命中目录套餐返回 (套餐价, 套餐名)，否则返回 (单点总价, '')。

    麦当劳没有固定折扣，套餐价以目录里真实套餐（--live 时由 MCP 回填）为准。
    """
    single = _price_of(items, names)
    meal = _MEAL_BY_COMBO.get(frozenset(names))
    if meal:
        return meal.price, meal.name
    return single, ""


def _what_text(names: List[str], combo: float, save: float, meal_name: str, kind: str) -> str:
    """「这是什么」文案：命中套餐说套餐名+价；无对应套餐按单点计（不虚构折扣）。"""
    joined = "+".join(names)
    if meal_name:
        tail = f"（省 ¥{save}）" if save > 0 else "（与单点同价）"
        return f"{joined} = {meal_name} ¥{combo}{tail}"
    return f"{joined} {kind} ¥{combo}（无对应套餐，按单点计）"


def _need_signal(items: Dict[str, Item], names: List[str]) -> str:
    """挑一个元素里真实存在的痛点属性，用于关联需求。"""
    for sig in ("满减", "单品券", "高热量", "解馋", "低卡"):
        if any(sig in items[n].attributes for n in names):
            return sig
    return ""


# 类别 → (默认角色, 属性依据)
_ROLE_ATTR = {
    "主食": ("主菜", "主食"),
    "饮品": ("饮品", "解渴"),
    "小食": ("配菜", "解馋"),
    "甜品": ("甜品", "甜"),
    "券": ("优惠", "券"),
}


def _erole(name: str, items: Dict[str, Item], role: str = "") -> dict:
    """给单品一个角色 + 有效属性依据（保证检查器第 3 条能核到属性）。"""
    it = items[name]
    r, a = _ROLE_ATTR.get(it.domain, ("参与", it.attributes[0] if it.attributes else "参与"))
    if role:
        r = role
    if a not in it.attributes:
        a = it.attributes[0] if it.attributes else "参与"
    return {"item": name, "role": r, "attribute": a}


def _finding(main: str, dm: str, combo: float, save: float, kind: str) -> str:
    """一句发现（≤30 字），主推不同措辞不同（位置敏感性）；省只在 save>0 才说。"""
    head = "当主菜" if dm == "主食" else "当主角"
    if save > 0:
        return f"{main}{head}，{kind} ¥{combo} 省 ¥{save}"
    return f"{main}{head}，{kind} ¥{combo}"


def _mk(tid, main, need_signal, what, finding, replaces, elements, eroles,
        manual, mv, failures, feasibility="feasible"):
    return {
        "template_id": tid,
        "main": main,
        "need_signal": need_signal,
        "what": what,
        "一句发现": finding,
        "replaces": replaces,
        "elements": elements,
        "element_roles": eroles,
        "说明书": manual,
        "最小验证": mv,
        "失败点": failures,
        "可行性": feasibility,
    }


# ---------------------------------------------------------------------------
# 位置依据（按真实坐标动态生成）
# ---------------------------------------------------------------------------

def _pos_label(name: str, pos: str) -> str:
    """坐标转措辞：在中心 / 相邻（无「在」）/ 在对角 / 在边角。"""
    if not pos:
        return "未定位"
    r, c = (int(x) for x in pos.split(","))
    if (r, c) == (2, 2):
        return "在中心"
    manhattan = abs(r - 2) + abs(c - 2)
    cheb = max(abs(r - 2), abs(c - 2))
    if manhattan == 1:
        return "相邻"
    if cheb == 1:
        return "在对角"
    return "在边角"


def build_basis(elements: List[str], eroles: List[dict], positions: Dict[str, str],
                mode: str) -> str:
    """按真实坐标拼位置依据；no_position 不声称任何位置。"""
    if mode == "no_position" or not positions:
        return "未使用位置语义"
    role_of = {er["item"]: er.get("role", "参与") for er in eroles}
    parts = []
    for name in elements:
        p = positions.get(name)
        if not p:
            continue
        role = role_of.get(name, "参与")
        parts.append(f"{name}{_pos_label(name, p)}={role}")
    return "；".join(parts)


# ---------------------------------------------------------------------------
# 合成 builder
# ---------------------------------------------------------------------------

def build_food(main, aux, items):
    """任意单品当主推，从 aux 里找互补类别，合成套餐/组合。

    组合价用 _combo_of：命中目录套餐取真实套餐价，否则按单点总价，绝不虚构折扣。
    """
    specs = []
    dm = items[main].domain
    rest = [a for a in aux if items[a].domain in FOOD_DOMAINS]
    by = {"主食": [], "小食": [], "饮品": [], "甜品": []}
    for a in rest:
        by[items[a].domain].append(a)
    have = {c: (list(by[c]) + ([main] if dm == c else [])) for c in FOOD_DOMAINS}

    def emit(tid, names, kind, manual_body, mv, failures):
        single = _price_of(items, names)
        combo, meal_name = _combo_of(items, names)
        save = round(single - combo, 1)
        cal = _cal_of(items, names)
        what = _what_text(names, combo, save, meal_name, kind)
        finding = _finding(main, dm, combo, save, kind)
        manual = list(manual_body) + [
            f"计价 ¥{combo}" + (f"（{meal_name}）" if meal_name else "（无对应套餐，按单点计）"),
            f"热量约 {cal} kcal",
        ]
        return _mk(
            tid, main, _need_signal(items, names),
            what=what, finding=finding,
            replaces=("逐件单点" if not meal_name else "单点计价"),
            elements=names,
            eroles=[_erole(n, items, role="主推") if n == main else _erole(n, items)
                    for n in names],
            manual=manual, mv=mv, failures=failures,
        )

    # 三件套：主食 + 小食 + 饮品
    for m in have["主食"]:
        for s in have["小食"]:
            for d in have["饮品"]:
                specs.append(emit("trio", [m, s, d], "三件套",
                                  [f"点主食 {m}", f"配小食 {s}", f"加饮品 {d}"],
                                  "看是否命中套餐、套餐价与单点谁低",
                                  ["套餐不能换成想要的小食", "饮品不能换零度"]))

    # 双件套：主食 + 饮品
    for m in have["主食"]:
        for d in have["饮品"]:
            specs.append(emit("duo_md", [m, d], "两件套",
                              [f"点主食 {m}", f"加饮品 {d}"],
                              "看两件是否有对应套餐、套餐价与单点谁低",
                              ["不含小食，可能不够吃"]))

    # 双件套：主食 + 小食
    for m in have["主食"]:
        for s in have["小食"]:
            specs.append(emit("duo_ms", [m, s], "两件套",
                              [f"点主食 {m}", f"加小食 {s}"],
                              "看两件是否有对应套餐、套餐价与单点谁低",
                              ["没有饮品，容易口干"]))

    # 下午茶：饮品 + 甜品
    for d in have["饮品"]:
        for w in have["甜品"]:
            specs.append(emit("tea_dw", [d, w], "下午茶",
                              [f"点饮品 {d}", f"加甜品 {w}"],
                              "看这个搭配是否解馋又划算",
                              ["没有主食，下午茶撑不住正餐"]))

    # 解馋组合：小食 + 甜品
    for s in have["小食"]:
        for w in have["甜品"]:
            specs.append(emit("snack_sw", [s, w], "解馋组合",
                              [f"点小食 {s}", f"加甜品 {w}"],
                              "看这个组合是否解馋又划算",
                              ["都是零食，热量偏高"]))

    return specs


def build_coupon(main, aux, items):
    """优惠券当主推：满减凑单 / 单品券直减，算出券后价。"""
    info = COUPONS.get(main)
    if not info:
        return []
    specs = []
    foods = [a for a in aux if items[a].domain in FOOD_DOMAINS]

    if info["kind"] == "满减":
        thr, off = info["threshold"], info["off"]
        for k in range(1, len(foods) + 1):
            for combo in combinations(foods, k):
                names = list(combo)
                single = _price_of(items, names)
                if single < thr:
                    continue
                pay = round(single - off, 1)
                specs.append(_mk(
                    "coupon_full", main, "满减",
                    what=f"用{main}凑 {'+'.join(names)}（¥{single}）→ 券后 ¥{pay}",
                    finding=f"凑满 ¥{thr}，{main} 正好用掉省 ¥{off}",
                    replaces="券过期浪费",
                    elements=[main] + names,
                    eroles=[_erole(main, items)] + [_erole(n, items) for n in names],
                    manual=[f"选 {'+'.join(names)}", f"凑到 ¥{single} 过门槛",
                            f"用{main}减 ¥{off}", f"实付约 ¥{pay}"],
                    mv="看券后价是否比不用券低",
                    failures=["没凑满门槛用不了", "券与其它券不能叠加"],
                ))
    else:  # 单品半价 / 单品免费
        target = info["target"]
        for t in [a for a in foods if a == target]:
            single = items[t].price
            off = single if info["kind"] == "单品免费" else round(single / 2, 1)
            pay = round(max(single - off, 0.0), 1)
            specs.append(_mk(
                "coupon_item", main, "单品券",
                what=f"用{main}买{t}：原价 ¥{single}，券后 ¥{pay}",
                finding=f"{t}有券，别原价买，立省 ¥{off}",
                replaces="原价买单品",
                elements=[main, t],
                eroles=[_erole(main, items), _erole(t, items)],
                manual=[f"选 {t}", f"用 {main}", f"实付约 ¥{pay}"],
                mv="看券后价是否为最低",
                failures=["券限单品，别的用不了"],
            ))
    return specs


def _builder_for(main: str, items: Dict[str, Item]):
    it = items.get(main)
    if not it:
        return None
    if it.domain == "券":
        return build_coupon
    if it.domain in FOOD_DOMAINS:
        return build_food
    return None


# ---------------------------------------------------------------------------
# 枚举子集 × main
# ---------------------------------------------------------------------------

def _subsets(names: List[str], min_size: int, max_size: int):
    out = []
    for k in range(min_size, max_size + 1):
        out.extend(combinations(names, k))
    return out


def match_all(items: Dict[str, Item], roles: Dict[str, str],
              positions: Dict[str, str], mode: str = "full") -> List[dict]:
    """枚举 2/3 元素子集 × 每个元素当 main，调用对应 builder，去重汇总。"""
    names = list(items.keys())
    specs: List[dict] = []
    seen = set()
    # 位置语义里的「主物」优先当 main（full 模式中心格；shuffled 模式置换后）
    for subset in _subsets(names, 2, 3):
        mains = sorted(subset, key=lambda n: (roles.get(n) != "main", subset.index(n)))
        for main in mains:
            builder = _builder_for(main, items)
            if builder is None:
                continue
            aux = [n for n in subset if n != main]
            for s in builder(main, aux, items):
                key = (tuple(sorted(s["elements"])), s["what"])
                if key in seen:
                    continue
                seen.add(key)
                specs.append(s)
    return specs
