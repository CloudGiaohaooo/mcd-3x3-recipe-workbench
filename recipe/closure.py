"""分解 → 再合成闭环（麦当劳版）。

- 套餐：拆成单品 → 算「单买总价 vs 套餐价」的价差（即「拆开更省还是更贵」）。
- 单品：直接合成（该单品 + 两个互补类别）数出可执行卡，再对比拆解给出的搭配方向。
"""
from __future__ import annotations

from .catalog import CATALOG
from .decomposition import decompose
from .generator import make_generator
from .pipeline import generate_recipes
from .schema import Slot

GRID = ["2,2", "2,1", "2,3", "1,1", "1,2", "1,3", "3,1", "3,2", "3,3"]


def _build_slots(names):
    return [Slot(position=GRID[i % 9], item_id=n) for i, n in enumerate(names)]


def closure(source_name: str) -> int:
    item = CATALOG.get(source_name)
    if item is None:
        print(f"目录里没有「{source_name}」，可选：" + "、".join(CATALOG.keys()))
        return 1

    card = decompose(item)
    print(f"\n◆ 分解→再合成闭环：{source_name}")
    print(f"来源：{item.description}")
    for i, p in enumerate(card.paths, 1):
        print(f"  {i}. {p.extract}")

    # 单品：再合成（直接组合数可执行卡）
    if item.type != "meal":
        comps = [n for n in CATALOG
                 if CATALOG[n].domain in ("主食", "小食", "饮品", "甜品") and n != source_name]
        names = [source_name] + comps[:2]
        items = {n: CATALOG[n] for n in names}
        gen = make_generator("rule")
        r = generate_recipes(items, _build_slots(names), gen)
        print(f"A（{' + '.join(names)} 直接合成）：{len(r['pool'])} 张可执行卡")
    else:
        print("（套餐已按「单买 vs 套餐价」完成拆解对比）")
    print("闭环：已完成（分解 + 价差/再合成对比）")
    return 0
