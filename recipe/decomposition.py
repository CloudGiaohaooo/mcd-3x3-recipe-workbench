"""第二阶段：分解台（麦当劳版）——反向拆解套餐。

输入一个套餐（type="meal"），拆成单品，算「单买总价 vs 套餐价」的价差；
输入一个单品，给出「能怎么搭配」的方向。危险项只拦截，不展开步骤。
"""
from __future__ import annotations

from typing import List

from .catalog import CATALOG
from .relations import DANGER_KEYWORDS
from .schema import DecomPath, DecompositionCard, Item


def _dangerous(item: Item) -> List[str]:
    attrs = item.attributes + item.side_effects
    return [kw for kw in DANGER_KEYWORDS if any(kw in a for a in attrs)]


def _cat_label(item: Item) -> str:
    return item.domain


def decompose(source: Item, mode: str = "new") -> DecompositionCard:
    blocked = _dangerous(source)
    paths: List[DecomPath] = []

    if not blocked and source.type == "meal" and source.constraints:
        parts = [n for n in source.constraints if n in CATALOG]
        single_total = round(sum(CATALOG[n].price for n in parts), 1)
        combo_price = source.price
        saving = round(single_total - combo_price, 1)

        for n in parts:
            p = CATALOG[n]
            paths.append(DecomPath(
                extract=f"单品：{n}（单买 ¥{p.price}，{p.calories} kcal）",
                how=[f"把 {n} 单独点", f"单买价 ¥{p.price}"],
                reversibility="reversible",
                reuse=f"想减量就单独点 {n}，不想就不点",
                risks=["单买可能更贵"],
                min_validation=f"对比套餐价 ¥{combo_price} 与单买价 ¥{p.price}",
                failure_modes=[f"{n} 单买不划算"],
            ))

        if saving > 0:
            verdict = f"单买总价 ¥{single_total} vs 套餐价 ¥{combo_price} → 套餐省 ¥{saving}"
        elif saving < 0:
            verdict = f"单买总价 ¥{single_total} vs 套餐价 ¥{combo_price} → 单买反而省 ¥{-saving}"
        else:
            verdict = f"单买总价 ¥{single_total} vs 套餐价 ¥{combo_price} → 价格持平"
        paths.append(DecomPath(
            extract=f"价差结论：{verdict}",
            how=["整套点套餐", "或逐项单买", "选总价更低的方式"],
            reversibility="reversible",
            reuse="用价差决定点套餐还是单点",
            risks=["套餐份量固定，不能随意替换"],
            min_validation="看两笔总价哪个低",
            failure_modes=["为了凑套餐多点了不需要的"],
        ))
    elif not blocked:
        # 单品：给搭配方向
        paths.append(DecomPath(
            extract=f"搭配方向：{source.name} 的常见组合",
            how=["配一个主食 + 一个饮品", "或配一个小食 + 一个甜品"],
            reversibility="reversible",
            reuse=f"把 {source.name} 作为套餐里的 {_cat_label(source)}",
            risks=["热量叠加"],
            min_validation="看搭配后总价/热量是否可控",
            failure_modes=["搭出热量过高的一餐"],
        ))

    if not paths:
        paths.append(DecomPath(
            extract="（暂无安全分解路径）",
            how=["无"],
            reversibility="irreversible",
            reuse="不建议拆",
            risks=["未知"],
            min_validation="无",
            failure_modes=["无"],
        ))

    return DecompositionCard(
        decomposition_id=f"d-{source.name}",
        source_item=source.name,
        paths=paths[:9],
        dangerous_items_blocked=blocked,
    )
