"""阶段 1：关系图（麦当劳版）。

只出单品/券之间的关系，不生成配方；关系必须来自物品属性（类别/券类型）。
每条关系写清：哪几个物品、关系是什么、依据哪个属性、是否危险。
"""
from __future__ import annotations

from typing import Dict, List

from .schema import Item, Relation

# 属性对 → 关系类型（对称：两件物品各持一个属性即成立）
RELATION_RULES = [
    (("主食", "饮品"), "搭配"),
    (("主食", "小食"), "搭配"),
    (("小食", "饮品"), "搭配"),
    (("饮品", "甜品"), "搭配"),
    (("小食", "甜品"), "搭配"),
    (("主食", "主食"), "替换"),
    (("券", "主食"), "券适用"),
    (("券", "饮品"), "券适用"),
    (("券", "小食"), "券适用"),
    (("券", "甜品"), "券适用"),
]

# 危险关键词（麦当劳域基本不触发，保留与检查器一致的拦截能力）
DANGER_KEYWORDS = [
    "电池", "高压", "破皮电线", "裸露电线", "绝缘",
    "清洁剂", "入口", "非食品容器",
    "密码", "账号", "数据外泄",
    "破解", "绕过授权", "侵权",
    "高温", "尖锐", "承重不足",
]


def _is_dangerous_attr(attrs: List[str]) -> bool:
    return any(kw in a for a in attrs for kw in DANGER_KEYWORDS)


def build_relations(items: Dict[str, Item]) -> List[Relation]:
    """对物品两两匹配属性对，产出关系。"""
    names = list(items.keys())
    relations: List[Relation] = []
    idx = 1
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            ia, ib = items[a], items[b]
            for (attrs, rel_type) in RELATION_RULES:
                if attrs[0] in ia.attributes and attrs[1] in ib.attributes:
                    relations.append(Relation(
                        relation_id=f"r{idx}",
                        items=[a, b],
                        relation=rel_type,
                        basis=[attrs[0], attrs[1]],
                        is_hard_explanation=False,
                        is_dangerous=_is_dangerous_attr(ia.attributes + ib.attributes),
                    ))
                    idx += 1
                elif attrs[1] in ia.attributes and attrs[0] in ib.attributes:
                    relations.append(Relation(
                        relation_id=f"r{idx}",
                        items=[a, b],
                        relation=rel_type,
                        basis=[attrs[1], attrs[0]],
                        is_hard_explanation=False,
                        is_dangerous=_is_dangerous_attr(ia.attributes + ib.attributes),
                    ))
                    idx += 1
    return relations


def filter_dangerous(relations: List[Relation]) -> List[Relation]:
    """危险关系拦截，不进入后续。"""
    return [r for r in relations if not r.is_dangerous]


def hard_explanation_count(relations: List[Relation]) -> int:
    return sum(1 for r in relations if r.is_hard_explanation)
