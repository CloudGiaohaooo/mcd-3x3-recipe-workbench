"""阶段 0：需求发现（麦当劳版）。

从输入单品/券里找「真实存在的小麻烦」：省钱、纠结吃什么、券快过期、一个人吃不完。
规则版按「痛点属性」映射需求模板；找不到真实需求就直接告诉用户，不硬生成。
"""
from __future__ import annotations

from typing import Dict, List

from .schema import Item, Need

# 痛点属性 → 需求模板（description 里的 {x} 会被替换成物品名）
NEED_RULES = [
    ("高热量", "{x} 想吃又怕热量超标", "想控制热量的人", "摄入超标、后悔"),
    ("满减", "{x} 快过期还没用掉", "领了券的人", "优惠浪费、多花钱"),
    ("单品券", "{x} 限单品，单点凑不齐", "有券的人", "券用不上"),
    ("解馋", "下午饿了纠结吃什么", "下午饿的人", "乱点更贵、热量更高"),
    ("可分享", "一个人点太多吃不完", "一个人点餐的人", "吃不完浪费"),
    ("低卡", "想解馋又不想超标", "控糖的人", "摄入超标"),
]


def discover_needs(items: Dict[str, Item]) -> List[Need]:
    """从物品属性里找需求候选（每个一句话）。"""
    needs: List[Need] = []
    seen = set()
    idx = 1
    for attr, desc_tpl, who, cost in NEED_RULES:
        hits = [name for name, it in items.items() if attr in it.attributes]
        if not hits:
            continue
        for name in hits:
            key = (attr, name)
            if key in seen:
                continue
            seen.add(key)
            needs.append(Need(
                need_id=f"n{idx}",
                description=desc_tpl.replace("{x}", name),
                who_forgets=who,
                cost_if_forgotten=cost,
                related_item_attributes=[attr],
            ))
            idx += 1
    return needs


def find_need_by_signal(needs: List[Need], signal: str) -> str:
    """按痛点属性回找需求 id，供候选关联使用。"""
    for n in needs:
        if signal in n.related_item_attributes:
            return n.need_id
    return ""
