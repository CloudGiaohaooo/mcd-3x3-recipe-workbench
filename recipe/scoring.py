"""排序打分（六项，各自不超过规范权重上限，总分 ≤ 100）。

需求真实度 25 + 惊喜/跨类 25 + 替代感 20 + 今晚可做 15 + 说明书完整 10 + 位置依据 5。
位置依据按「主材料是否命中格子里的主物角色」给 5 或 0：位置因此进入排序，
但不越界加成一个第七项。
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from .schema import Candidate, Item, Need, ScoreDetail
from .position import PositionContext

STRONG_PAIN = {"会烂", "易埋包里", "易缠"}


def score(candidate: Candidate, items: Dict[str, Item], needs: List[Need],
          position_ctx: PositionContext) -> Tuple[int, ScoreDetail]:
    d = ScoreDetail()
    card = candidate.card

    # 需求真实度 25
    need = next((n for n in needs if n.need_id == candidate.need_id), None)
    if need:
        d.need = 25 if any(a in STRONG_PAIN for a in need.related_item_attributes) else 20
    elif card.get("一句发现"):
        d.need = 12  # 没有直接需求，但有具体场景

    # 惊喜/跨类 25
    domains = {items[n].domain for n in candidate.elements if n in items and items[n].domain}
    roles = {er.get("role") for er in candidate.element_roles}
    if len(domains) >= 3:
        d.surprise = 25
    elif len(domains) == 2:
        d.surprise = 20
    else:
        d.surprise = 15 + (2 if len(roles) >= 3 else 0)

    # 替代感 20
    if candidate.replaces:
        d.replacement = 20 if len(candidate.replaces) >= 4 else 16

    # 今晚可做 15
    d.doable_tonight = 15 if card.get("可行性", "feasible") == "feasible" else 10

    # 说明书完整度 10
    manual = card.get("说明书", [])
    if len(manual) >= 4:
        d.manual_complete = 10
    elif len(manual) >= 3:
        d.manual_complete = 8
    else:
        d.manual_complete = 5
    joined = "".join(manual)
    if any(w in joined for w in ["适当", "若干", "一些", "适量"]):
        d.manual_complete -= 1

    # 位置依据 5：主材料命中「主物」角色（中心/置换后）即满分，否则 0
    main_role = position_ctx.roles_by_item.get(candidate.main_item, "")
    d.position_evidence = 5 if main_role == "main" else 0

    total = (d.need + d.surprise + d.replacement + d.doable_tonight
             + d.manual_complete + d.position_evidence)
    return total, d
