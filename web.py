"""麦门 3×3 配方工作台 —— Web 前端服务（纯标准库，零第三方依赖）。

用法：
    python web.py                 # 默认 http://127.0.0.1:8765
    python web.py --port 9000

打开浏览器即可用拖拽把单品放进 3×3 九宫格，合成套餐 / 反向分解 / 看单品详情。
价格/热量默认是离线占位值；点「实时数据」（需 MCD_MCP_TOKEN）可拉麦当劳 MCP 真实数据。

接口：
    GET  /                前端页面
    GET  /api/menu        目录（单品/券/套餐）
    GET  /api/item?name=  单品产品档案
    POST /api/compose     合成（items:[{name,position}] → 配方卡池）
    POST /api/decompose   分解（name → 产品档案 + 分解路径）
    POST /api/live        拉麦当劳 MCP 真实数据回填目录（city/keyword）
    GET  /api/health      状态
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from recipe.catalog import CATALOG, COUPONS
from recipe.decomposition import decompose, item_profile
from recipe.generator import make_generator
from recipe.live import enrich_catalog, fetch_live
from recipe.mcp_client import McpClient
from recipe.pipeline import generate_recipes
from recipe.schema import Slot

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
LIVE_ACTIVE = False

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def _setup_encoding():
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _note():
    return ("价格/热量/套餐构成来自麦当劳 MCP 实时数据" if LIVE_ACTIVE
            else "价格/热量为离线示例占位值，接 MCP 后为真实值")


def menu_payload():
    items = []
    for name, it in CATALOG.items():
        d = asdict(it)
        d["name"] = name
        items.append(d)
    # 按 domain 顺序分组，前端直接渲染
    order = ["主食", "小食", "饮品", "甜品", "券", "套餐"]
    groups = {g: [x for x in items if x["domain"] == g] for g in order}
    return {
        "ok": True,
        "items": items,
        "groups": groups,
        "order": order,
        "coupons": COUPONS,
        "live": LIVE_ACTIVE,
        "note": _note(),
    }


def compose_payload(body: dict):
    raw = body.get("items") or []
    if not isinstance(raw, list) or len(raw) < 2:
        return {"ok": False, "error": "至少放 2 个单品进九宫格（合成需要 2–3 个）。"}
    items, slots, seen_pos = {}, [], set()
    for e in raw:
        name = e.get("name") if isinstance(e, dict) else None
        pos = e.get("position") if isinstance(e, dict) else None
        if name not in CATALOG:
            return {"ok": False, "error": f"目录里没有「{name}」。"}
        r, c = (int(x) for x in str(pos).split(",")) if pos and "," in str(pos) else (0, 0)
        if not (1 <= r <= 3 and 1 <= c <= 3):
            return {"ok": False, "error": f"「{name}」的位置 {pos} 不在 3×3 内。"}
        if pos in seen_pos:
            return {"ok": False, "error": f"位置 {pos} 被重复占用。"}
        seen_pos.add(pos)
        items[name] = CATALOG[name]
        slots.append(Slot(position=str(pos), item_id=name))

    position_mode = body.get("position_mode") or "full"
    if position_mode not in ("full", "no_position", "shuffled", "roles_only"):
        position_mode = "full"

    generator = make_generator("rule")
    result = generate_recipes(
        items, slots, generator,
        mode="new", position_mode=position_mode,
        max_candidates=20, max_retries=5, max_pool=5, time_limit=30,
    )

    cards = [asdict(c) for c in result["pool"]]
    relations = [{"id": r.relation_id, "items": r.items,
                  "relation": r.relation, "basis": r.basis}
                 for r in result["relations"]]
    position_note = result["position_ctx"].sensitivity_note if result["position_ctx"] else ""
    return {
        "ok": True,
        "cards": cards,
        "best": asdict(result["best"]) if result["best"] else None,
        "message": result["message"],
        "stop_reason": result["stop_reason"],
        "stats": result["stats"],
        "position_note": position_note,
        "needs": [asdict(n) for n in result["needs"]],
        "relations": relations,
        "live": LIVE_ACTIVE,
        "note": _note(),
    }


def decompose_payload(name: str):
    item = CATALOG.get(name)
    if not item:
        return {"ok": False, "error": f"目录里没有「{name}」，可选：" + "、".join(CATALOG.keys())}
    return {
        "ok": True,
        "profile": item_profile(item),
        "decomposition": asdict(decompose(item, mode="new")),
        "live": LIVE_ACTIVE,
        "note": _note(),
    }


def live_payload(body: dict):
    global LIVE_ACTIVE
    client = McpClient()
    if not client.available:
        return {"ok": False, "error": "未设置 MCD_MCP_TOKEN 环境变量，无法接入麦当劳 MCP。"}
    city = body.get("city") or "北京市"
    keyword = body.get("keyword") or "天安门"
    live = fetch_live(client, city, keyword)
    if not live.store:
        return {"ok": False, "error": "门店解析失败：" + "；".join(live.errors)}
    notes = enrich_catalog(CATALOG, live)
    LIVE_ACTIVE = True
    return {
        "ok": True,
        "store": live.summary(),
        "notes": notes,
        "errors": live.errors,
        "price_check": live.price_check,
        "coupons": live.coupons,
        "counts": {
            "prices": len(live.menu_prices),
            "nutrition": len(live.nutrition_kcal),
            "meals": len(live.meal_components),
        },
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "MCD3x3/1.0"

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n <= 0:
                return {}
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._serve_static("index.html")
        elif path == "/api/health":
            client = McpClient()
            self._json({"ok": True, "live_available": client.available,
                        "live_active": LIVE_ACTIVE})
        elif path == "/api/menu":
            self._json(menu_payload())
        elif path == "/api/item":
            qs = parse_qs(parsed.query)
            name = (qs.get("name") or [""])[0]
            item = CATALOG.get(name)
            if not item:
                self._json({"ok": False, "error": f"目录里没有「{name}」。"}, 404)
            else:
                self._json({"ok": True, "profile": item_profile(item),
                            "live": LIVE_ACTIVE, "note": _note()})
        else:
            self._serve_static(path.lstrip("/"))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json()
        try:
            if path == "/api/compose":
                self._json(compose_payload(body))
            elif path == "/api/decompose":
                self._json(decompose_payload(body.get("name") or ""))
            elif path == "/api/live":
                self._json(live_payload(body))
            else:
                self._json({"ok": False, "error": "未知接口 " + path}, 404)
        except Exception as exc:  # 不让任何异常把服务带崩
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    def _serve_static(self, rel: str):
        if rel in ("", "index.html"):
            rel = "index.html"
        rel = rel.split("?")[0]
        target = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not target.startswith(WEB_DIR) or not os.path.isfile(target):
            self._json({"ok": False, "error": "404 Not Found"}, 404)
            return
        ext = os.path.splitext(target)[1].lower()
        with open(target, "rb") as f:
            self._send(200, f.read(), MIME.get(ext, "application/octet-stream"))

    def log_message(self, fmt, *args):
        sys.stdout.write("  %s %s\n" % (self.address_string(), fmt % args))


def main():
    _setup_encoding()
    ap = argparse.ArgumentParser(description="麦门 3×3 配方工作台 Web 服务")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    args = ap.parse_args()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print("=" * 60)
    print("  麦门 3×3 配方工作台 · 前端已启动")
    print(f"  打开浏览器访问： http://{args.host}:{args.port}")
    print("  · 拖拽单品进九宫格 → 合成套餐；点「分解」看单品详情")
    print("  · 点「实时数据」接麦当劳 MCP（需 MCD_MCP_TOKEN 环境变量）")
    print("=" * 60)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
