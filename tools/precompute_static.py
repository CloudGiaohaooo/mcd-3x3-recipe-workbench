"""把动态后端预计算成静态 JSON，供 GitHub Pages 纯静态演示使用。

用法（在项目根目录）：
    python tools/precompute_static.py

产出 static/data/：
    menu.json         目录（等价 /api/menu）
    decompose.json    全部单品的分解 + 产品档案（等价 /api/decompose）
    compose.json      全部 2~3 单品组合 × 中心主推 的合成结果（等价 /api/compose）
                        键格式： "<中心单品名>::<排序后的单品名,逗号分隔>"
                        值： { cards:[...], message }（不含位置依据，前端按实际坐标重算）

说明：合成引擎是确定性的；配方只取决于「放了哪几样」+「哪样在中心(主推)」，
非中心格子的具体位置只影响「位置依据」文案，故前端按真实坐标重算该句即可。
"""
from __future__ import annotations

import json
import os
import sys
from itertools import combinations

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dataclasses import asdict                        # noqa: E402
from recipe.catalog import CATALOG, COUPONS           # noqa: E402
from recipe.decomposition import decompose, item_profile  # noqa: E402
from recipe.generator import make_generator           # noqa: E402
from recipe.pipeline import generate_recipes          # noqa: E402
from recipe.schema import Slot                        # noqa: E402

OUT = os.path.join(ROOT, "static", "data")
os.makedirs(OUT, exist_ok=True)

NAMES = list(CATALOG.keys())
GENERATOR = make_generator("rule")

# 非中心格子的规范化占位坐标（只用于确定“非中心”角色，实际位置由前端重算）
_AUX_POS = ["2,1", "2,3", "1,2", "3,2", "1,1", "1,3", "3,1", "3,3"]


def _slots(items: dict, center: str):
    slots = [Slot(position="2,2", item_id=center)]
    others = [n for n in items if n != center]
    for i, n in enumerate(others):
        slots.append(Slot(position=_AUX_POS[i % len(_AUX_POS)], item_id=n))
    return slots


def _menu_payload():
    items = []
    for name, it in CATALOG.items():
        d = it.__dict__.copy()
        d["name"] = name
        items.append(d)
    order = ["主食", "小食", "饮品", "甜品", "券", "套餐"]
    groups = {g: [x for x in items if x["domain"] == g] for g in order}
    return {"ok": True, "items": items, "groups": groups, "order": order,
            "coupons": COUPONS, "live": False, "note": "价格/热量为离线示例占位值"}


def _trim_cards(result: dict, main_map: dict):
    cards = []
    for c in result["pool"]:
        key = (tuple(sorted(c.参与元素)), c.这是什么)
        cards.append({
            "score": c.score,
            "score_detail": c.score_detail.__dict__,
            "一句发现": c.一句发现,
            "这是什么": c.这是什么,
            "替代了什么": c.替代了什么,
            "参与元素": c.参与元素,
            "剔除清单": c.剔除清单,
            "说明书": c.说明书,
            "最小验证": c.最小验证,
            "失败点": c.失败点,
            "main_item": main_map.get(key, (c.参与元素 or [""])[0]),
        })
    return {"cards": cards, "message": result["message"]}


def _compose(items: dict, center: str):
    slots = _slots(items, center)
    result = generate_recipes(items, slots, GENERATOR, mode="new",
                              position_mode="full", max_candidates=20,
                              max_retries=5, max_pool=5, time_limit=30)
    # 从生成器候选里取 main_item（配方卡本身不携带该字段）
    main_map = {}
    if result.get("position_ctx") is not None:
        candidates = GENERATOR.generate(items, slots, result["needs"],
                                        result["relations"], result["position_ctx"], "new")
        main_map = {(tuple(sorted(c.elements)), c.what): c.main_item for c in candidates}
    return _trim_cards(result, main_map)


def main():
    # 1) 菜单
    with open(os.path.join(OUT, "menu.json"), "w", encoding="utf-8") as f:
        json.dump(_menu_payload(), f, ensure_ascii=False)

    # 2) 分解 / 详情
    decomp = {}
    for name, it in CATALOG.items():
        decomp[name] = {
            "profile": item_profile(it),
            "decomposition": asdict(decompose(it, mode="new")),
            "live": False, "note": "价格/热量为离线示例占位值",
        }
    with open(os.path.join(OUT, "decompose.json"), "w", encoding="utf-8") as f:
        json.dump(decomp, f, ensure_ascii=False)

    # 3) 合成：2/3 单品组合 × 中心选择
    compose = {}
    count = 0
    for k in (2, 3):
        for subset in combinations(NAMES, k):
            items = {n: CATALOG[n] for n in subset}
            for center in subset:
                key = f"{center}::{','.join(sorted(subset))}"
                compose[key] = _compose(items, center)
                count += 1
    with open(os.path.join(OUT, "compose.json"), "w", encoding="utf-8") as f:
        json.dump(compose, f, ensure_ascii=False)

    # 统计
    def mb(p):
        return os.path.getsize(p) / 1024 / 1024
    print(f"menu.json      {mb(os.path.join(OUT, 'menu.json')):.2f} MB")
    print(f"decompose.json {mb(os.path.join(OUT, 'decompose.json')):.2f} MB")
    print(f"compose.json   {mb(os.path.join(OUT, 'compose.json')):.2f} MB  ({count} 条)")
    nonempty = sum(1 for v in compose.values() if v["cards"])
    print(f"有配方结果的组合：{nonempty} / {count}")


if __name__ == "__main__":
    main()
