"""麦门 3×3 配方工作台 —— 命令行入口。

把 1–9 个麦当劳单品 / 优惠券放进 3×3 格子，合成性价比套餐 / 反向拆解套餐。

用法：
  python run.py                     # 交互：选场景 → 出卡 → 换一个 / 就这个 / 标记
  python run.py --demo              # 非交互跑全部示例
  python run.py --scenario 巨无霸薯条可乐
  python run.py --ablation shuffled # 位置消融：打乱位置看套餐是否变化
  python run.py --decompose 巨无霸套餐    # 反向拆解：套餐拆成单品算价差
  python run.py --closure 巨无霸套餐      # 分解 → 再合成闭环

价格/热量当前为示例占位值；接入麦当劳 MCP 后改由 calculate-price / list-nutrition-foods 拉真实数据。
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import asdict

from recipe.catalog import CATALOG
from recipe.closure import closure
from recipe.decomposition import decompose
from recipe.feedback import load_positive_samples, record_feedback
from recipe.generator import make_generator
from recipe.live import enrich_catalog, fetch_live
from recipe.mcp_client import McpClient
from recipe.pipeline import generate_recipes
from recipe.schema import Slot

# 内置示例场景：物品名 -> 位置（r,c，1 起）
SCENARIOS = {
    "巨无霸薯条可乐": [("巨无霸", "2,2"), ("薯条", "2,1"), ("可乐", "3,2")],
    "可乐薯条巨无霸·主辅反转": [("可乐", "2,2"), ("薯条", "2,1"), ("巨无霸", "3,2")],
    "满30减5券巨无霸可乐": [("满30减5券", "2,2"), ("巨无霸", "2,1"), ("可乐", "3,2")],
    "薯条免费券薯条可乐": [("薯条免费券", "2,2"), ("薯条", "2,1"), ("可乐", "3,2")],
    "麦旋风可乐苹果派": [("麦旋风", "2,2"), ("可乐", "2,1"), ("苹果派", "3,2")],
}

DISCLAIMER = "（价格/热量为示例占位值，接入麦当劳 MCP 后拉真实数据）"
LIVE_NOTE = "（价格/热量/套餐构成来自麦当劳 MCP 实时数据）"
LIVE = False  # --live 成功拉取后被置 True，决定卡片里显示哪种来源注记


def _setup_encoding():
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _apply_live(args):
    """--live：调麦当劳 MCP 拉真实数据回填目录；失败则降级离线并返回 None。"""
    global LIVE
    client = McpClient()
    if not client.available:
        print("⚠ 未设置 MCD_MCP_TOKEN 环境变量，--live 降级为离线示例数据。")
        print("  设置：set MCD_MCP_TOKEN=<Token>  （Windows） / export MCD_MCP_TOKEN=... （macOS/Linux）")
        return None
    live = fetch_live(client, args.city, args.keyword)
    if not live.store:
        print("⚠ 实时门店解析失败，--live 降级为离线示例数据。")
        for e in live.errors:
            print("  - " + e)
        return None
    notes = enrich_catalog(CATALOG, live)
    print("=" * 64)
    print("麦当劳 MCP 实时数据已接入 · " + live.summary())
    print("=" * 64)
    print("· 菜单（query-meals）：%d 个目录单品/套餐命中真实价" % len(live.menu_prices))
    print("· 热量（list-nutrition-foods）：%d 个单品命中真实营养表" % len(live.nutrition_kcal))
    print("· 套餐构成（query-meal-detail）：" + ("、".join(live.meal_components) or "无"))
    for n in notes:
        print("    " + n)
    if live.price_check:
        pc = live.price_check
        det = " + ".join(f"{p.get('productName','')}¥{p.get('subtotal',0)/100:.1f}" for p in pc["list"])
        print("· calculate-price 真实计价验证：" + det + f" = ¥{pc['price_yuan']}（分→元）")
    if live.coupons:
        print("· 门店可用券（query-store-coupons）：")
        for c in live.coupons:
            prods = "、".join(p.get("productName", "") for p in (c.get("products") or []))
            cid = (c.get("couponId") or "")[:8]
            print(f"    - {c.get('title')}（{prods}）有效期 {c.get('tradeDateTime')} couponId={cid}…")
    else:
        print("· 门店可用券：当前门店无可用券")
    print("· 券说明：合成场景里的满减/单品券是示例券；真实券后价走 calculate-price 的 items[].couponId")
    for e in live.errors:
        print("  ⚠ " + e)
    print("=" * 64)
    print()
    LIVE = True
    return live


def build_input(scenario: str):
    items = {name: CATALOG[name] for name, _ in SCENARIOS[scenario]}
    slots = [Slot(position=pos, item_id=name) for name, pos in SCENARIOS[scenario]]
    return items, slots


def print_card(card, index=None):
    tag = f"  [{index}/{card.score}分]" if index is not None else ""
    print("─" * 60)
    print(f"【一句发现】{card.一句发现}")
    print(f"【这是什么】{card.这是什么}")
    print(f"【替代了什么】{card.替代了什么}")
    print(f"【参与元素】{' + '.join(card.参与元素)}")
    print(f"【剔除清单】" + "；".join(f"{e['item']}：{e['reason']}" for e in card.剔除清单) or "无")
    print(f"【说明书】")
    for i, step in enumerate(card.说明书, 1):
        print(f"    {i}. {step}")
    print(f"【最小验证】{card.最小验证}")
    print(f"【失败点】" + "；".join(card.失败点))
    print(f"【位置依据】{card.位置依据}")
    print(f"【可行性】{card.可行性}    【分数】{card.score}/100    【来源】{card.source}{tag}")
    sd = card.score_detail
    print(f"【打分】需求{sd.need} 惊喜{sd.surprise} 替代{sd.replacement} "
          f"可做{sd.doable_tonight} 说明书{sd.manual_complete} 位置{sd.position_evidence}")
    print("─" * 60)


def print_pipeline_meta(result, verbose=False):
    if not verbose:
        return
    print("\n== 阶段 0 需求 ==")
    for n in result["needs"]:
        print(f"  · {n.description}（谁会：{n.who_forgets}；会怎样：{n.cost_if_forgotten}）")
    print("== 阶段 1 关系图 ==")
    for r in result["relations"]:
        print(f"  · {r.relation_id} {'+'.join(r.items)} → {r.relation}（依据：{'、'.join(r.basis)}）")
    print("== 位置语义 ==")
    if result["position_ctx"]:
        for s in result["position_ctx"].slots:
            print(f"  · {s.position} {s.item} → {s.role or '-'} ({s.confidence})")
    if result["retry_log"]:
        print("== 回退日志 ==")
        for lg in result["retry_log"]:
            print(f"  · {lg.get('candidate')} {lg.get('reason', lg.get('failed_rules'))} {lg.get('suggestion','')}")


def run_one(scenario, args):
    items, slots = build_input(scenario)
    generator = make_generator(args.provider)

    def _call(gen):
        return generate_recipes(
            items, slots, gen,
            mode=args.mode,
            position_mode=args.ablation,
            max_candidates=args.max_candidates,
            max_retries=args.max_retries,
            max_pool=args.max_pool,
            time_limit=args.time_limit,
        )

    try:
        result = _call(generator)
    except Exception as exc:
        if args.provider != "deepseek":
            raise
        print(f"\n  ⚠ DeepSeek 调用失败，回退规则生成器：{type(exc).__name__}: {exc}")
        result = _call(make_generator("rule"))
    print(f"\n◆ 场景：{scenario}（mode={args.mode}, 位置={args.ablation}）")
    print("   输入：" + "  ".join(f"{n}@{p}" for n, p in SCENARIOS[scenario]))
    print_pipeline_meta(result, verbose=args.verbose)

    if not result["pool"]:
        print(f"\n  {result['message']}")
        return

    if result["message"]:
        print(f"\n  （提示）{result['message']}")

    print(f"\n  合格池共 {result['pool_size']} 张，只展示最优 1 张：\n")
    return result


def regenerate(scenario, args):
    items, slots = build_input(scenario)
    generator = make_generator(args.provider)
    return generate_recipes(
        items, slots, generator,
        mode=args.mode,
        position_mode=args.ablation,
        max_candidates=args.max_candidates,
        max_retries=args.max_retries,
        max_pool=args.max_pool,
        time_limit=args.time_limit,
    )


def interactive(args):
    print("可用的麦当劳单品 / 券 / 套餐：" + "、".join(CATALOG.keys()))
    print("场景：")
    for i, name in enumerate(SCENARIOS, 1):
        print(f"  {i}. {name}")
    choice = input("选场景编号（回车=巨无霸薯条可乐）：").strip()
    name = list(SCENARIOS)[int(choice) - 1] if choice.isdigit() and 1 <= int(choice) <= len(SCENARIOS) else "巨无霸薯条可乐"

    result = run_one(name, args)
    if not result or not result["pool"]:
        return
    pool = result["pool"]
    viewed = {0}
    idx = 0
    print_card(pool[0])
    while True:
        cmd = input("（换一个 / 就这个 / 标记 / 再生成一批 / 退出）：").strip()
        if cmd in ("退出", "q", "exit"):
            break
        if cmd == "换一个":
            nxt = None
            for i in range(len(pool)):
                if i not in viewed:
                    nxt = i
                    break
            if nxt is None:
                result2 = regenerate(name, args)
                if result2 and result2["pool"]:
                    pool = result2["pool"]
                    viewed = {0}
                    idx = 0
                    print("池已刷新，重新生成一批：")
                    print_card(pool[0])
                else:
                    print("池空了，没有更多合格结果，减一个单品再试。")
                continue
            viewed.add(nxt)
            idx = nxt
            print_card(pool[idx], index=f"{len(viewed)}/{len(pool)}")
        elif cmd == "就这个":
            record_feedback(pool[idx].recipe_id, user_mark="surprising", outcome="not_tried",
                            card=asdict(pool[idx]))
            print(f"已记录「就这个」→ 正样本库（{pool[idx].recipe_id}）。")
        elif cmd == "标记":
            mark = input("有惊喜 / 一般 / 扯：").strip()
            mapping = {"有惊喜": "surprising", "一般": "normal", "扯": "bullshit"}
            record_feedback(pool[idx].recipe_id, user_mark=mapping.get(mark, "normal"),
                            outcome="not_tried", card=asdict(pool[idx]))
            print("已记录反馈。")
        elif cmd == "再生成一批":
            result2 = regenerate(name, args)
            if result2 and result2["pool"]:
                pool = result2["pool"]
                viewed = {0}
                idx = 0
                print_card(pool[0])
            else:
                print("没有新的合格结果。")
        else:
            print("输入：换一个 / 就这个 / 标记 / 再生成一批 / 退出")


def run_demo(args):
    note = LIVE_NOTE if LIVE else DISCLAIMER
    print("=" * 60)
    print("麦门 3×3 配方工作台 — Demo " + note)
    print("=" * 60)
    for name in SCENARIOS:
        result = run_one(name, args)
        if result and result["pool"]:
            print_card(result["pool"][0])
        print()


def run_my_recipes():
    entries = load_positive_samples()
    if not entries:
        print("我的配方还是空的")
        return
    print(f"我的配方（正样本库）共 {len(entries)} 条：")
    for i, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            continue
        card = entry.get("card")
        if isinstance(card, dict):
            print(f"  {i}. 一句发现：{card.get('一句发现', '')}")
            print(f"     这是什么：{card.get('这是什么', '')}")
            print(f"     来源：{card.get('source', entry.get('user_mark', 'old'))}")
        else:
            print(f"  {i}. 一句发现：（旧记录，无完整卡片）")


def run_decompose(name, args):
    item = CATALOG.get(name)
    if not item:
        print(f"目录里没有「{name}」，可选：" + "、".join(CATALOG.keys()))
        return
    card = decompose(item, mode=args.mode)
    note = LIVE_NOTE if LIVE else DISCLAIMER
    print(f"\n◆ 分解台：{name} " + note)
    if card.dangerous_items_blocked:
        print(f"  ⚠ 危险项拦截（不展开步骤）：{card.dangerous_items_blocked}")
    for i, p in enumerate(card.paths, 1):
        print(f"  {i}. {p.extract}")
        print(f"     怎么拆：{' → '.join(p.how)}")
        print(f"     可逆性：{p.reversibility}   再利用：{p.reuse}")
        print(f"     风险：{'、'.join(p.risks)}   最小验证：{p.min_validation}")
        print(f"     失败点：{'、'.join(p.failure_modes)}")


def main():
    _setup_encoding()
    ap = argparse.ArgumentParser(description="麦门 3×3 配方工作台")
    ap.add_argument("--scenario", help="内置场景名")
    ap.add_argument("--demo", action="store_true", help="非交互跑全部示例")
    ap.add_argument("--live", action="store_true", help="调麦当劳 MCP 拉真实菜单/营养/券/计价（需 MCD_MCP_TOKEN）")
    ap.add_argument("--city", default="北京市", help="--live 时定位门店的城市（默认北京市）")
    ap.add_argument("--keyword", default="天安门", help="--live 时定位门店的地标关键词（默认天安门）")
    ap.add_argument("--decompose", help="对目录里的单品/套餐跑分解台")
    ap.add_argument("--closure", help="对目录里的单品/套餐跑分解→再合成闭环")
    ap.add_argument("--my-recipes", action="store_true", help="打印正样本库里的「我的配方」")
    ap.add_argument("--mode", default="old", choices=["new", "old", "independent"])
    ap.add_argument("--provider", default="rule", choices=["rule", "deepseek"])
    ap.add_argument("--ablation", default="full", choices=["full", "no_position", "shuffled", "roles_only"])
    ap.add_argument("--max-candidates", type=int, default=20)
    ap.add_argument("--max-retries", type=int, default=5)
    ap.add_argument("--max-pool", type=int, default=3)
    ap.add_argument("--time-limit", type=int, default=30)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.live:
        _apply_live(args)

    if args.decompose:
        run_decompose(args.decompose, args)
    elif args.closure:
        sys.exit(closure(args.closure))
    elif args.my_recipes:
        run_my_recipes()
    elif args.demo:
        run_demo(args)
    elif args.scenario:
        result = run_one(args.scenario, args)
        if result and result["pool"]:
            print_card(result["pool"][0])
    else:
        interactive(args)


if __name__ == "__main__":
    main()
