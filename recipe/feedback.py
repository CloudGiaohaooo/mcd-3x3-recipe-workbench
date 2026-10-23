"""反馈回流骨架。

用户标「有惊喜 / 一般 / 扯」；「扯」进负样本库，「有惊喜」进正样本库；
记录「做成了 / 失败了 / 卡在哪 / 改了什么」。持久化到 data/ 下的 JSON。
"""
from __future__ import annotations

import json
import os
from typing import List

from .negative_samples import BUILTIN_NEGATIVE_SAMPLES

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

NEG_FILE = os.path.join(DATA_DIR, "negative_samples.json")
POS_FILE = os.path.join(DATA_DIR, "positive_samples.json")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback_log.json")


def _load(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _save(path: str, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_negative_samples() -> List[str]:
    stored = _load(NEG_FILE, [])
    return list(dict.fromkeys(BUILTIN_NEGATIVE_SAMPLES + stored))


def load_positive_samples() -> List[dict]:
    return _load(POS_FILE, [])


def load_feedback_log() -> List[dict]:
    return _load(FEEDBACK_FILE, [])


def build_failure_graph() -> dict:
    """读 feedback_log，按 missing_condition 聚合 outcome=failed 的记录；
    写 DATA_DIR/failure_graph.json，返回 {条件: 次数}。"""
    graph: dict = {}
    for entry in load_feedback_log():
        if entry.get("outcome") == "failed" and entry.get("missing_condition"):
            cond = entry["missing_condition"]
            graph[cond] = graph.get(cond, 0) + 1
    _save(os.path.join(DATA_DIR, "failure_graph.json"), graph)
    return graph


def record_feedback(recipe_id: str, user_mark: str = "normal", outcome: str = "not_tried",
                    stuck_at: str = "", changed: str = "", missing_condition: str = "",
                    card: dict | None = None) -> dict:
    """记录一条反馈，并按标记回流到负/正样本库。

    card 不为空时，把完整配方卡存进 entry（key 用 card），供「旧」模式召回；
    不传 card 时行为与之前一致。
    """
    entry = {
        "recipe_id": recipe_id,
        "user_mark": user_mark,
        "outcome": outcome,
        "stuck_at": stuck_at,
        "changed": changed,
        "missing_condition": missing_condition,
    }
    if card:
        entry["card"] = card
    log = load_feedback_log()
    log.append(entry)
    _save(FEEDBACK_FILE, log)

    if user_mark == "bullshit":
        neg = load_negative_samples()
        label = f"{recipe_id}：{stuck_at}" if stuck_at else recipe_id
        if label not in neg:
            neg.append(label)
        _save(NEG_FILE, [x for x in neg if x not in BUILTIN_NEGATIVE_SAMPLES])
    elif user_mark == "surprising":
        pos = load_positive_samples()
        pos.append(entry)
        _save(POS_FILE, pos)
    return entry
