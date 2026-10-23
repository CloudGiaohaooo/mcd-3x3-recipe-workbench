"""位置语义模块（麦当劳版）。

位置不是界面装饰，是生成约束：同一组单品换位置，必须得到不同配方（主辅反转）。
predict() 读 item.attributes，按「物品能力 × 格子角色」给角色先验。

模式（用于消融实验）：
- full        能力 + 位置 + 角色预测
- no_position 关闭位置：不读格子，只给物品列表（roles 为空）
- shuffled    打乱：按 seed 置换 items→positions，角色跟着新坐标重算
- roles_only  只给格子角色，不给能力描述

角色集合：main / auxiliary / trigger / record / spread / witness / constraint。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .schema import Item, Slot

CENTER = (2, 2)
ROLES = ["main", "auxiliary", "trigger", "record", "spread", "witness", "constraint"]

ROLE_MEANING = {
    "main": "主菜/核心单品",
    "auxiliary": "搭配/辅助",
    "trigger": "触发",
    "record": "记录",
    "spread": "传播",
    "witness": "见证",
    "constraint": "约束/场景",
}

# 单品能力 → 角色语义（读 item.attributes 后给出，用于「能力 × 角色」先验）
CAPABILITY_ROLE = {
    "主食": "主菜", "饱腹": "主菜", "高热量": "主菜",
    "小食": "配菜", "解馋": "配菜", "可分享": "配菜",
    "饮品": "饮品", "解渴": "饮品",
    "甜品": "甜品", "甜": "甜品",
    "满减": "优惠", "折扣": "优惠", "单品券": "优惠", "券": "优惠",
    "低卡": "低卡", "无糖": "无糖", "辣": "风味", "海鲜": "风味",
}


@dataclass
class SlotRole:
    position: str
    role: str
    confidence: float
    item: str


@dataclass
class PositionContext:
    mode: str
    slots: List[SlotRole] = field(default_factory=list)
    roles_by_item: Dict[str, str] = field(default_factory=dict)
    positions_by_item: Dict[str, str] = field(default_factory=dict)
    sensitivity_note: str = ""


def _parse(pos: str):
    r, c = pos.split(",")
    return int(r), int(c)


def _geometry_role(pos: str) -> tuple:
    """按格子几何位置给角色先验（中心/相邻/对角/边角）。"""
    r, c = _parse(pos)
    if (r, c) == CENTER:
        return "main", 0.9
    manhattan = abs(r - 2) + abs(c - 2)
    cheb = max(abs(r - 2), abs(c - 2))
    if manhattan == 1:
        return "auxiliary", 0.8
    if cheb == 1:
        return "spread", 0.7
    return "constraint", 0.6


def _capability_role(item: Item) -> str:
    """读 item.attributes，返回能力对应的角色语义（无则空）。"""
    if item is None:
        return ""
    for attr in item.attributes:
        if attr in CAPABILITY_ROLE:
            return CAPABILITY_ROLE[attr]
    return ""


def _shuffled_positions(slots: List[Slot], seed: int) -> Dict[str, str]:
    """按 seed 生成原坐标的确定性置换：n≥2 时至少移动 2 个物品（轮换一格全换）。"""
    n = len(slots)
    items = [s.item_id for s in slots]
    positions = [s.position for s in slots]
    if n < 2:
        return {items[0]: positions[0]} if n else {}
    offset = 1 + (int(seed) % (n - 1))
    return {items[i]: positions[(i + offset) % n] for i in range(n)}


def predict(items: Dict[str, Item], slots: List[Slot], mode: str = "full",
            seed: int = 0) -> PositionContext:
    """给每个格子输出候选角色 + 置信度；不同模式用于消融。

    full        原坐标不变。
    shuffled    按 seed 真的置换 items→positions，角色跟着新坐标重算。
    no_position 关闭位置，不给角色。
    roles_only  只给格子角色，不给能力描述。
    """
    ctx = PositionContext(mode=mode)

    # shuffled 真换坐标，其余模式恒为原始坐标
    if mode == "shuffled":
        ctx.positions_by_item = _shuffled_positions(slots, seed)
    else:
        ctx.positions_by_item = {s.item_id: s.position for s in slots}

    if mode == "no_position":
        ctx.slots = [SlotRole(position=s.position, role="", confidence=0.0, item=s.item_id)
                     for s in slots]
        ctx.roles_by_item = {}
        ctx.sensitivity_note = "位置语义已关闭，本组不依据位置生成。"
        return ctx

    # 角色名与置信度按「每个物品的实际坐标」重算（shuffled 用置换后的坐标）
    geo_role = {n: _geometry_role(p)[0] for n, p in ctx.positions_by_item.items()}
    geo_conf = {n: _geometry_role(p)[1] for n, p in ctx.positions_by_item.items()}
    roles_by_item = dict(geo_role)

    # 能力 × 格子角色：能力角色读自 item.attributes，并入非主物角色的语义标签
    for n, p in ctx.positions_by_item.items():
        role = roles_by_item.get(n, "")
        cap = _capability_role(items.get(n))
        conf = geo_conf.get(n, 0.0)
        if role and role != "main" and cap:
            role = f"{role}:{cap}"
            roles_by_item[n] = role
        ctx.slots.append(SlotRole(position=p, role=role, confidence=conf, item=n))

    ctx.roles_by_item = roles_by_item

    if mode == "roles_only":
        ctx.sensitivity_note = "只给格子角色，不给能力描述（消融对照组）。"
    else:
        parts = []
        for it, r in roles_by_item.items():
            meaning = ROLE_MEANING.get(r, r)
            parts.append(f"{it}={meaning}")
        ctx.sensitivity_note = "；".join(parts) if parts else ""
    return ctx
