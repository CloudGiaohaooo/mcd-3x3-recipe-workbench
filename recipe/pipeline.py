"""流水线编排。

用户输入 1–9 个物品及位置
→ 阶段 0 需求发现 → 阶段 1 关系图 → 阶段 2 候选生成 → 阶段 3 检查器
→ 通过进合格池 / 不通过回退（只减不增）
→ 合格池 ≥ 3 才停 → 排序打分 → 只展示最高分 1 张。
"""
from __future__ import annotations

import time
from typing import Dict, List

from .checker import check, intercept_danger
from .generator import RecipeGenerator
from .needs import discover_needs
from .position import predict
from .relations import build_relations, filter_dangerous, hard_explanation_count
from .schema import Candidate, Item, RecipeCard, Slot
from .scoring import score


def _sig(c: Candidate):
    return (tuple(sorted(c.elements)), c.what)


def reduce_elements(items: Dict[str, Item], remove_count: int = 1):
    """回退（只减不增）：去掉最靠后的元素，重生成更小组合。"""
    names = list(items.keys())
    if len(names) <= 2:
        return None
    reduced = dict(items)
    for name in names[-remove_count:]:
        reduced.pop(name, None)
    return reduced


def _build_card(c: Candidate, total: int, detail, check_result) -> RecipeCard:
    check_log = [
        {"通过项": f"规则 {d.rule}", "证据": d.evidence}
        for d in check_result.details if d.result == "pass"
    ]
    return RecipeCard(
        recipe_id=c.candidate_id,
        一句发现=c.card.get("一句发现", ""),
        这是什么=c.what,
        替代了什么=c.replaces,
        参与元素=c.elements,
        剔除清单=c.card.get("剔除清单", []),
        说明书=c.card.get("说明书", []),
        最小验证=c.card.get("最小验证", ""),
        失败点=c.card.get("失败点", []),
        位置依据=c.card.get("位置依据", ""),
        可行性=c.card.get("可行性", "needs_check"),
        source=c.source,
        score=total,
        score_detail=detail,
        check_log=check_log,
        retry_count=0,
    )


def generate_recipes(items: Dict[str, Item], slots: List[Slot], generator: RecipeGenerator,
                     mode: str = "new", max_candidates: int = 20, max_retries: int = 5,
                     max_pool: int = 3, time_limit: int = 30,
                     position_mode: str = "full") -> dict:
    start = time.time()
    pool: List[RecipeCard] = []
    retries = 0
    candidates_generated = 0
    retry_log: List[dict] = []
    seen = set()
    stop_reason = "pool_full"

    # 阶段 0：需求发现
    needs = discover_needs(items)
    if not needs:
        return _result([], None, needs, [], None, retry_log,
                       "这组东西暂时没找到值得做的小事，建议换一组或减元素。",
                       "no_need", {})

    # 阶段 1：关系图（至少有一对可搭配关系即可；两个单品也能合成，如 饮品+甜品=下午茶）
    relations = build_relations(items)
    if not relations or hard_explanation_count(relations) > 1:
        return _result([], None, needs, relations, None, retry_log,
                       "这组物品之间关系不足，建议换一组或减元素。",
                       "insufficient_relations", {})
    relations = filter_dangerous(relations)

    position_ctx = predict(items, slots, mode=position_mode)
    working_items = dict(items)

    # 阶段 2–3：生成 + 检查 + 回退（只减不增）
    while True:
        if len(pool) >= max_pool:
            stop_reason = "pool_full"
            break
        if candidates_generated >= max_candidates:
            stop_reason = "max_candidates"
            break
        if retries >= max_retries:
            stop_reason = "max_retries"
            break
        if time.time() - start > time_limit:
            stop_reason = "time_limit"
            break

        candidates = generator.generate(working_items, slots, needs, relations,
                                        position_ctx, mode)
        new = [c for c in candidates if _sig(c) not in seen]
        if not new:
            # 只减不增：无新候选时减一个元素再生成
            reduced = reduce_elements(working_items, 1)
            if reduced is None:
                stop_reason = "no_new_candidates"
                break
            working_items = reduced
            retries += 1
            retry_log.append({"candidate": "-", "reason": "reduce_elements",
                              "detail": f"减到 {list(working_items)}"})
            continue

        for c in new:
            seen.add(_sig(c))
        candidates_generated += len(new)

        for c in new:
            blocked, msg, danger_type = intercept_danger(c, working_items)
            if blocked:
                retry_log.append({"candidate": c.candidate_id, "reason": "danger",
                                  "detail": danger_type})
                continue
            result = check(c, working_items, relations, needs)
            if result.passed:
                total, detail = score(c, working_items, needs, position_ctx)
                pool.append(_build_card(c, total, detail, result))
            else:
                retries += 1
                retry_log.append({"candidate": c.candidate_id,
                                  "failed_rules": result.failed_rules,
                                  "suggestion": result.suggestion})

    pool.sort(key=lambda x: x.score, reverse=True)
    pool = _dedup(pool)

    stats = {
        "candidates_generated": candidates_generated,
        "retries": retries,
        "stop_reason": stop_reason,
        "passed": len(pool),
        "failed": len(retry_log),
    }

    if not pool:
        return _result([], None, needs, relations, position_ctx, retry_log,
                       "这组暂时没找到能过检的合成，建议换一组或减元素。",
                       stop_reason, stats)

    message = ""
    if len(pool) < max_pool:
        message = "这组选择不多，要不要减一个物品再试？"
    return _result(pool, pool[0], needs, relations, position_ctx, retry_log,
                   message, stop_reason, stats)


def _dedup(pool: List[RecipeCard]) -> List[RecipeCard]:
    """同一「做什么 + 参与元素组合」只保留最高分。"""
    best = {}
    for card in pool:
        key = (tuple(sorted(card.参与元素)), card.这是什么)
        if key not in best or card.score > best[key].score:
            best[key] = card
    return sorted(best.values(), key=lambda x: x.score, reverse=True)


def _result(pool, best, needs, relations, position_ctx, retry_log, message,
            stop_reason, stats):
    return {
        "pool": pool,
        "best": best,
        "needs": needs,
        "relations": relations,
        "position_ctx": position_ctx,
        "retry_log": retry_log,
        "message": message,
        "pool_size": len(pool),
        "stop_reason": stop_reason,
        "stats": stats,
    }
