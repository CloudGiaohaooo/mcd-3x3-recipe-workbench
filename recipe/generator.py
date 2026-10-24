"""阶段 2：候选生成。

统一接口 RecipeGenerator.generate(...) -> List[Candidate]。
- RuleBasedGenerator：确定性规则/模板生成，离线可跑（默认）。
- DeepSeekGenerator：接 deepseek-chat（OpenAI 兼容接口），可切换，需 DEEPSEEK_API_KEY。
架构上留「模型可替换层」，生成器与检查器可各自独立实现。
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List

from . import templates
from .feedback import load_positive_samples
from .needs import find_need_by_signal
from .schema import Candidate, Excluded, Item, Need, Relation, Slot
from .position import CAPABILITY_ROLE, PositionContext

MIN_CAND = 8
MAX_CAND = 10


def _relation_ids_for(relations: List[Relation], elements: List[str]) -> List[str]:
    """返回元素组合涉及的关系 id。"""
    eset = set(elements)
    return [r.relation_id for r in relations if set(r.items) <= eset]


class RecipeGenerator:
    """生成器统一接口（可替换层）。"""

    def generate(self, items: Dict[str, Item], slots: List[Slot], needs: List[Need],
                 relations: List[Relation], position_ctx: PositionContext,
                 mode: str = "new") -> List[Candidate]:
        raise NotImplementedError


class RuleBasedGenerator(RecipeGenerator):
    """规则/模板生成器：确定性、离线、可复现。"""

    def generate(self, items, slots, needs, relations, position_ctx, mode="new"):
        positions = position_ctx.positions_by_item
        specs = templates.match_all(
            items, position_ctx.roles_by_item, positions, position_ctx.mode
        )
        all_names = list(items.keys())

        candidates: List[Candidate] = []
        for i, s in enumerate(specs, start=1):
            elements = s["elements"]
            excluded = [Excluded(item=name, reason=f"与「{s['what']}」无关")
                        for name in all_names if name not in elements]
            need_id = find_need_by_signal(needs, s["need_signal"])
            basis = templates.build_basis(elements, s["element_roles"], positions,
                                          position_ctx.mode)
            card = {
                "一句发现": s["一句发现"][:30],
                "这是什么": s["what"],
                "替代了什么": s["replaces"],
                "参与元素": elements,
                "剔除清单": [{"item": e.item, "reason": e.reason} for e in excluded],
                "说明书": s["说明书"],
                "最小验证": s["最小验证"],
                "失败点": s["失败点"],
                "位置依据": basis,
                "可行性": s["可行性"],
                "save": s.get("save", 0.0),
            }
            candidates.append(Candidate(
                candidate_id=f"c{i}",
                what=s["what"],
                elements=elements,
                replaces=s["replaces"],
                excluded=excluded,
                relation_ids=_relation_ids_for(relations, elements),
                need_id=need_id,
                element_roles=s["element_roles"],
                card=card,
                source=mode,
                main_item=s["main"],
            ))

        # 确定性裁剪：主材料命中「主物」者优先，元素多者优先，再按生成顺序；封顶 MAX_CAND
        candidates.sort(key=lambda c: (
            position_ctx.roles_by_item.get(c.main_item) != "main",
            -len(c.elements),
        ))
        # 「旧」模式：读正样本库，把存了 card 的旧卡真正带回候选，排在规则候选前
        if mode == "old":
            recalled = self._recall_old(
                load_positive_samples(), relations, items, position_ctx
            )
            seen = {(tuple(sorted(c.elements)), c.what) for c in candidates}
            olds: List[Candidate] = []
            for oc in recalled:
                key = (tuple(sorted(oc.elements)), oc.what)
                if key in seen:
                    continue
                seen.add(key)
                olds.append(oc)
            candidates = olds + candidates
        return candidates[:MAX_CAND]

    def _recall_old(self, entries, relations, items, position_ctx) -> List[Candidate]:
        """从正样本库把存了完整配方卡（card）的旧配方还原成 Candidate，旧卡优先。"""
        olds: List[Candidate] = []
        for i, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                continue
            card = entry.get("card")
            if not isinstance(card, dict):
                continue
            what = (card.get("这是什么") or "").strip()
            raw_elements = card.get("参与元素") or []
            if not what or not isinstance(raw_elements, list):
                continue
            elements = [e for e in raw_elements if isinstance(e, str) and e.strip()]
            if not elements:
                continue
            # 旧卡的参与元素必须都在当前物品里，否则落不回当前场景
            if not all(e in items for e in elements):
                continue
            excluded: List[Excluded] = []
            raw_excluded = card.get("剔除清单") or []
            if isinstance(raw_excluded, list):
                for e in raw_excluded:
                    if isinstance(e, dict):
                        item = (e.get("item") or "").strip()
                        reason = (e.get("reason") or "无关").strip()
                    else:
                        item = str(e).strip()
                        reason = "无关"
                    if item and item not in elements:
                        excluded.append(Excluded(item=item, reason=reason))
            main_item = next((e for e in elements
                              if position_ctx.roles_by_item.get(e) == "main"), elements[0])
            olds.append(Candidate(
                candidate_id=f"old{i}",
                what=what,
                elements=elements,
                replaces=card.get("替代了什么") or "",
                excluded=excluded,
                relation_ids=_relation_ids_for(relations, elements),
                need_id="",
                element_roles=[],
                card=card,
                source="old",
                main_item=main_item,
            ))
        return olds


class DeepSeekGenerator(RecipeGenerator):
    """DeepSeek 生成器：接 deepseek-chat，强制 JSON 输出。

    需要 openai 库 + 环境变量 DEEPSEEK_API_KEY。未安装/无 key 时抛出并提示回退。
    """

    def __init__(self, base_url="https://api.deepseek.com", model="deepseek-chat",
                 api_key_env="DEEPSEEK_API_KEY"):
        self.base_url = base_url
        self.model = model
        self.api_key = os.environ.get(api_key_env, "")

    def generate(self, items, slots, needs, relations, position_ctx, mode="new"):
        if not self.api_key:
            raise RuntimeError("未设置 DEEPSEEK_API_KEY，无法调用 DeepSeek；请改回规则生成器。")
        try:
            from openai import OpenAI  # 延迟导入，规则版不依赖
        except ImportError as e:
            raise RuntimeError("未安装 openai，请 `pip install openai` 后再用 DeepSeek 生成器。") from e

        system_prompt = (
            "你是麦当劳点餐助手。从顾客放进九宫格的单品/优惠券里，"
            "合成最划算的一餐或一个点单方案（套餐/两件套/下午茶/券后最优）。"
            "只输出一个 JSON 对象，格式："
            "{\"candidates\":[{\"what\":\"这是什么组合\",\"elements\":[\"单品名\"],"
            "\"replaces\":\"替代了什么（如 逐件单点/原价买）\",\"excluded\":[{\"item\":\"未用单品\","
            "\"reason\":\"无关|硬解释|缺可观测信号|危险|缺条件\"}],"
            "\"一句发现\":\"不超过30字\",\"说明书\":[\"点单步骤\"],"
            "\"最小验证\":\"\",\"失败点\":[\"\"],\"位置依据\":\"\"}]}。"
            "一次给 8–10 个候选；elements 至少 2 个；优先给出「券后更省」「套餐比单点划算」的方案；"
            "价格按输入里的价格字段计算，不要虚构折扣；不要输出思维链。"
        )
        user_input = json.dumps({
            "items": {k: {"attributes": v.attributes, "domain": v.domain,
                          "price": v.price, "calories": v.calories, "type": v.type}
                      for k, v in items.items()},
            "positions": [{"position": s.position, "item_id": s.item_id} for s in slots],
            "needs": [{"description": n.description} for n in needs],
            "relations": [{"items": r.items, "relation": r.relation} for r in relations],
            "mode": mode,
        }, ensure_ascii=False)

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            response_format={"type": "json_object"},
        )
        data = self._loads_json(resp.choices[0].message.content)
        return self._parse(data, mode, items, position_ctx)

    @staticmethod
    def _loads_json(text: str) -> dict:
        """容忍模型偶发的代码围栏/前后说明/尾逗号；仍失败就抛可读错误。"""
        text = (text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"\s*```$", "", text).strip()
        candidates = [text]
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            candidates.append(text[start:end + 1])
        for raw in candidates:
            for strict in (False, True):
                try:
                    obj = json.loads(raw, strict=strict)
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    pass
            try:
                fixed = re.sub(r",\s*([}\]])", r"\1", raw)
                obj = json.loads(fixed, strict=False)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"DeepSeek 返回的 JSON 无法解析：{text[:200]!r}")

    @staticmethod
    def _text(value) -> str:
        return value.strip() if isinstance(value, str) else ("" if value is None else str(value).strip())

    @staticmethod
    def _list(value) -> List[str]:
        if isinstance(value, list):
            return [DeepSeekGenerator._text(x) for x in value if DeepSeekGenerator._text(x)]
        if isinstance(value, str) and value.strip():
            parts = [p.strip() for p in value.replace("；", "\n").splitlines()]
            return [p for p in parts if p]
        return []

    def _parse(self, data: dict, mode: str, items: Dict[str, Item] | None = None,
               position_ctx: PositionContext | None = None) -> List[Candidate]:
        candidates: List[Candidate] = []
        raws = data.get("candidates", []) if isinstance(data, dict) else []
        if not isinstance(raws, list):
            return candidates
        for i, raw in enumerate(raws, start=1):
            if not isinstance(raw, dict):
                continue
            elements = []
            for e in raw.get("elements", []) if isinstance(raw.get("elements", []), list) else []:
                name = self._text(e.get("item") if isinstance(e, dict) else e)
                if name and name not in elements:
                    elements.append(name)
            excluded = []
            for e in raw.get("excluded", []) if isinstance(raw.get("excluded", []), list) else []:
                if isinstance(e, dict):
                    item = self._text(e.get("item", ""))
                    reason = self._text(e.get("reason", "")) or "无关"
                else:
                    item, reason = self._text(e), "无关"
                if item and item not in elements:
                    excluded.append(Excluded(item=item, reason=reason))
            # 模型漏写的未参与元素补成“无关”，避免悄悄丢掉；检查器仍会校验理由
            if items:
                have = {x.item for x in excluded}
                for name in items:
                    if name not in elements and name not in have:
                        excluded.append(Excluded(item=name, reason="无关"))

            what = self._text(raw.get("what", "")) or self._text(raw.get("一句发现", ""))
            if not what:
                continue
            finding = self._text(raw.get("一句发现", "")) or what
            manual = self._list(raw.get("说明书", []))
            failures = self._list(raw.get("失败点", []))
            feasibility = self._text(raw.get("可行性", "needs_check"))
            if feasibility not in ("feasible", "needs_check", "not_recommended"):
                feasibility = "needs_check"

            # 给模型候选补角色依据：读 item.attributes 的受控能力词；
            # 这样检查器第3条能核属性、第8条能看到角色分工。
            element_roles = []
            for name in elements:
                item = items.get(name) if items else None
                attr = ""
                if item:
                    attr = next((a for a in item.attributes if a in CAPABILITY_ROLE), "")
                role = CAPABILITY_ROLE.get(attr, "")
                if not role and position_ctx:
                    role = position_ctx.roles_by_item.get(name, "")
                if role and attr:
                    element_roles.append({"item": name, "role": role, "attribute": attr})
            main_item = ""
            if position_ctx:
                main_item = next((n for n in elements
                                  if position_ctx.roles_by_item.get(n) == "main"), "")
            if not main_item and elements:
                main_item = elements[0]

            candidates.append(Candidate(
                candidate_id=f"c{i}",
                what=what,
                elements=elements,
                replaces=self._text(raw.get("replaces", "")),
                excluded=excluded,
                element_roles=element_roles,
                main_item=main_item,
                card={
                    "一句发现": finding[:30],
                    "这是什么": what,
                    "替代了什么": self._text(raw.get("replaces", "")),
                    "参与元素": elements,
                    "剔除清单": [{"item": e.item, "reason": e.reason} for e in excluded],
                    "说明书": manual,
                    "最小验证": self._text(raw.get("最小验证", "")),
                    "失败点": failures,
                    "位置依据": self._text(raw.get("位置依据", "")),
                    "可行性": feasibility,
                },
                source=mode,
            ))
        return candidates


def make_generator(provider: str = "rule", **kwargs) -> RecipeGenerator:
    if provider == "deepseek":
        return DeepSeekGenerator(
            base_url=kwargs.get("base_url", "https://api.deepseek.com"),
            model=kwargs.get("model", "deepseek-chat"),
            api_key_env=kwargs.get("api_key_env", "DEEPSEEK_API_KEY"),
        )
    return RuleBasedGenerator()
