"""数据模型：材料、格子、需求、关系、候选、检查结果、配方卡、分解卡、反馈。

字段命名与《非算法部分》《算法部分》里的 JSON 结构保持一致。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List


@dataclass
class Item:
    id: str
    name: str
    type: str = "physical"  # physical|software|account|capability|data|process
    description: str = ""
    attributes: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    side_effects: List[str] = field(default_factory=list)
    observable_signals: List[str] = field(default_factory=list)
    domain: str = ""  # 麦门版：主食/小食/饮品/甜品/券/套餐
    price: float = 0.0       # 示例单价（占位；接入麦当劳 MCP 后改真实价）
    calories: int = 0        # 示例热量（占位）
    emoji: str = ""          # 前端图标
    tagline: str = ""        # 一句话卖点（宣传语，示例编辑内容，非 MCP）
    ingredients: List[str] = field(default_factory=list)  # 原料/配料（示例编辑内容，非 MCP）


@dataclass
class Slot:
    position: str  # "r,c"，从 1 开始
    item_id: str
    role: str = ""


@dataclass
class Need:
    need_id: str
    description: str
    who_forgets: str
    cost_if_forgotten: str
    related_item_attributes: List[str] = field(default_factory=list)


@dataclass
class Relation:
    relation_id: str
    items: List[str]
    relation: str
    basis: List[str]
    is_hard_explanation: bool = False
    is_dangerous: bool = False


@dataclass
class Excluded:
    item: str
    reason: str


@dataclass
class Candidate:
    candidate_id: str
    what: str
    elements: List[str]
    replaces: str
    excluded: List[Excluded] = field(default_factory=list)
    relation_ids: List[str] = field(default_factory=list)
    need_id: str = ""
    element_roles: List[Dict[str, str]] = field(default_factory=list)
    card: Dict[str, Any] = field(default_factory=dict)  # 完整配方卡字段
    source: str = "new"
    main_item: str = ""  # 主材料（用于「物品能力 × 格子角色」打分）


@dataclass
class RuleDetail:
    rule: int
    result: str  # pass|fail
    reason: str
    evidence: str


@dataclass
class CheckResult:
    candidate_id: str
    passed: bool
    failed_rules: List[int] = field(default_factory=list)
    details: List[RuleDetail] = field(default_factory=list)
    suggestion: str = ""


@dataclass
class ScoreDetail:
    need: int = 0
    surprise: int = 0
    replacement: int = 0
    doable_tonight: int = 0
    manual_complete: int = 0
    position_evidence: int = 0


@dataclass
class RecipeCard:
    recipe_id: str
    一句发现: str
    这是什么: str
    替代了什么: str
    参与元素: List[str]
    剔除清单: List[Dict[str, str]]
    说明书: List[str]
    最小验证: str
    失败点: List[str]
    位置依据: str
    可行性: str
    source: str = "new"
    score: int = 0
    score_detail: ScoreDetail = field(default_factory=ScoreDetail)
    check_log: List[Dict[str, Any]] = field(default_factory=list)
    retry_count: int = 0


@dataclass
class DecomPath:
    extract: str
    how: List[str]
    reversibility: str
    reuse: str
    risks: List[str]
    min_validation: str
    failure_modes: List[str]


@dataclass
class DecompositionCard:
    decomposition_id: str
    source_item: str
    paths: List[DecomPath]
    dangerous_items_blocked: List[str] = field(default_factory=list)


def to_dict(obj) -> Dict[str, Any]:
    return asdict(obj)
