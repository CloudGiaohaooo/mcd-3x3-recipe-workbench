"""阶段 3：检查器。

不是第二个生成器，不负责想新点子。只逐条过规则卡，判断这个候选能不能输出。
八条硬指标逐条给「通过/不通过 + 证据」；危险项在八条之前拦截。
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from .negative_samples import NEGATIVE_PATTERNS
from .schema import Candidate, CheckResult, Item, Need, Relation, RuleDetail

DANGER_GROUPS = [
    ("电气", ["电池", "高压", "破皮电线", "裸露电线", "绝缘"]),
    ("食品污染", ["清洁剂", "入口", "非食品容器"]),
    ("隐私", ["密码", "账号", "数据外泄"]),
    ("法律", ["破解", "绕过授权", "侵权"]),
    ("人身安全", ["高温", "尖锐", "承重不足"]),
]


def intercept_danger(candidate: Candidate, items: Dict[str, Item]) -> Tuple[bool, str, str]:
    """危险项在八条检查之前拦截。返回 (是否拦截, 提示, 危险类型)。"""
    text = candidate.what + "".join(candidate.elements)
    for name in candidate.elements:
        it = items.get(name)
        if it:
            text += "".join(it.attributes) + "".join(it.side_effects)
    for group, kws in DANGER_GROUPS:
        for kw in kws:
            if kw in text:
                return True, f"这个方向涉及 {group}，不建议自行尝试。需要专业处理。", group
    return False, "", ""


def check(candidate: Candidate, items: Dict[str, Item], relations: List[Relation],
          needs: List[Need]) -> CheckResult:
    """八条硬指标。"""
    details: List[RuleDetail] = []
    all_names = list(items.keys())

    # 1. 是一件事吗
    neg = [p for p in NEGATIVE_PATTERNS if p in candidate.what]
    if neg:
        details.append(RuleDetail(1, "fail", "这是活动/仪式/象征，不是一件事",
                                  f"文案命中负样本特征：{neg}"))
    elif not candidate.replaces:
        details.append(RuleDetail(1, "fail", "说不清替代什么",
                                  "没有替代物，像在描述一个动作而不是一件事"))
    else:
        details.append(RuleDetail(1, "pass", "一句话说清做什么、给谁、替代什么",
                                  f"做什么：{candidate.what}；替代：{candidate.replaces}"))

    # 2. 至少 2 个元素吗
    if len(candidate.elements) >= 2:
        details.append(RuleDetail(2, "pass", "参与元素 ≥ 2",
                                  f"参与 {len(candidate.elements)} 个：{candidate.elements}"))
    else:
        details.append(RuleDetail(2, "fail", "元素不足",
                                  f"只有 {len(candidate.elements)} 个参与元素"))

    # 3. 关系来自属性吗
    attr_ok = True
    bad_elem = []
    if candidate.element_roles:
        for er in candidate.element_roles:
            item = items.get(er["item"])
            if not item or er.get("attribute") not in item.attributes:
                attr_ok = False
                bad_elem.append(er["item"])
    else:
        # 没有角色依据时，退回到「是否出现在关系里」
        in_rel = {e for r in relations for e in r.items}
        bad_elem = [e for e in candidate.elements if e not in in_rel]
        attr_ok = not bad_elem
    if attr_ok:
        details.append(RuleDetail(3, "pass", "每个元素都能指到属性字段",
                                  "元素角色都有属性依据，硬解释 ≤ 1"))
    else:
        details.append(RuleDetail(3, "fail", "有元素是硬解释/贴标签",
                                  f"这些元素没有属性支持：{bad_elem}"))

    # 4. 有替代感吗
    if candidate.replaces and len(candidate.replaces) >= 2:
        details.append(RuleDetail(4, "pass", "替代了某个常用东西或做法",
                                  f"替代：{candidate.replaces}"))
    else:
        details.append(RuleDetail(4, "fail", "替代物不明确",
                                  "说不清没有它时人现在怎么做"))

    # 5. 今晚能做吗
    constraints = []
    for name in candidate.elements:
        it = items.get(name)
        if it:
            constraints += it.constraints
    need_wait = any(kw in ("".join(constraints)) for kw in ["采购", "定制", "等一周", "专业工具"])
    if not need_wait:
        details.append(RuleDetail(5, "pass", "不需买大件、不需等一周",
                                  "无采购/定制/等待/专业工具约束"))
    else:
        details.append(RuleDetail(5, "fail", "卡在条件", "需要采购、定制或等待"))

    # 6. 剔除清单完整吗
    excluded_names = [e.item for e in candidate.excluded]
    missing = [n for n in all_names if n not in candidate.elements and n not in excluded_names]
    vague = [e.item for e in candidate.excluded if e.reason in ("", "不需要")]
    if not missing and not vague:
        details.append(RuleDetail(6, "pass", "未参与元素都有理由",
                                  f"剔除 {len(candidate.excluded)} 个，理由合法"))
    else:
        details.append(RuleDetail(6, "fail", "剔除清单不完整",
                                  f"漏了 {missing or '无'}，理由模糊 {vague or '无'}"))

    # 7. 像负样本库吗
    text = candidate.what + candidate.card.get("一句发现", "")
    hit = [p for p in NEGATIVE_PATTERNS if p in text]
    if not hit:
        details.append(RuleDetail(7, "pass", "不像负样本库", "与负样本库逐条比对不命中"))
    else:
        details.append(RuleDetail(7, "fail", "像负样本库", f"命中：{hit}"))

    # 8. 有惊喜感吗
    domains = {items.get(n).domain for n in candidate.elements if items.get(n)}
    domains.discard(None)
    roles = {er.get("role") for er in candidate.element_roles}
    if len(domains) >= 2 or len(roles) >= 2:
        details.append(RuleDetail(8, "pass", "元素跨类或角色有分工，关系接得住",
                                  f"跨类 {domains or '无'}，角色 {roles or '无'}"))
    else:
        details.append(RuleDetail(8, "fail", "太同类/太顺", "元素单一类别且角色无分工"))

    failed = [d.rule for d in details if d.result == "fail"]
    suggestion = _suggest(candidate, failed, details)
    return CheckResult(
        candidate_id=candidate.candidate_id,
        passed=not failed,
        failed_rules=failed,
        details=details,
        suggestion=suggestion,
    )


def _suggest(candidate: Candidate, failed: List[int], details: List[RuleDetail]) -> str:
    if not failed:
        return ""
    if 1 in failed:
        return "减到核心两三个元素，说清『做什么、给谁、替代什么』，别做成活动或仪式。"
    if 4 in failed:
        return f"写清替代物：没有它时人现在怎么做（比如替代翻包乱摸）。"
    if 6 in failed:
        return "把未参与元素逐个写进剔除清单，理由只能是无关/硬解释/危险/缺条件。"
    if 3 in failed:
        return "换掉没有属性支持的元素，或改用有属性依据的组合。"
    if 2 in failed:
        return "至少保留 2 个参与元素。"
    if 8 in failed:
        return "换一个不同类别的元素，或让元素有不同分工。"
    return "对照不通过项，按规则卡调整后重生成。"
