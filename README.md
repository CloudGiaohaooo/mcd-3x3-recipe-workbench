# 麦门 3×3 配方工作台 · mcd-recipe-workbench

把麦当劳单品 / 优惠券 / 套餐放进 3×3 格子，合成性价比套餐、反向拆解套餐算价差。价格、热量、套餐构成、优惠券全部走麦当劳 MCP 实时拉取。

- **正向合成**：拖入单品/优惠券，生成「套餐 + 真实价 + 热量」配方卡
- **反向分解**：丢一个套餐，拆成单品，算「单买 vs 套餐」谁更省（真实价差）
- **位置敏感**：同一组单品换位置，主辅反转，配方就变
- **真实数据**：菜单 `query-meals`、营养 `list-nutrition-foods`、券 `query-store-coupons`、套餐构成 `query-meal-detail`、计价 `calculate-price`

> 参加麦当劳 1024 程序员创意开发大赛（2026）。详见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。

## 快速开始

```bash
# 离线模式（占位示例价，可复现）
python run.py --demo
python run.py --scenario 巨无霸薯条可乐
python run.py --ablation shuffled     # 位置消融
python run.py --decompose 巨无霸套餐  # 反向拆解套餐
python run.py --closure 巨无霸套餐    # 分解→再合成闭环

# 实时模式（真实数据，需设置 Token）
#   Windows: set MCD_MCP_TOKEN=<Token>   macOS/Linux: export MCD_MCP_TOKEN=<Token>
python run.py --live --demo
python run.py --live --scenario 巨无霸薯条可乐
python run.py --live --decompose 麦辣鸡腿堡套餐
python run.py --live --city 上海市 --keyword 外滩   # 换城市/门店
```

无 Token 时离线可复现；设了 `MCD_MCP_TOKEN` 加 `--live` 即切换真实数据，卡片会标注数据来源。

## 引擎

沿用 3×3 灵感合成台流水线：需求发现 → 关系图 → 候选生成 → 检查器（八条硬指标）→ 只减不增回退 → 合格池 → 排序 → 只展示最优 1 张。换域只改数据层（`catalog / templates / needs / relations / position / negative_samples / decomposition`），核心算法不变。

真实数据层在 `recipe/mcp_client.py`（纯标准库 JSON-RPC 客户端，Token 只读环境变量）与 `recipe/live.py`（门店解析 + 菜单/营养/券/套餐映射回填）。

## 比赛交付文件

- `README.md` — 项目介绍与使用
- `CONTEST_DECLARATION.md` — 参赛声明（官方原文）
- `MCP_INTEGRATION.md` — MCP 接入说明
- `mcp-config.example.json` — 脱敏配置示例（仅环境变量占位符）
- `recipe/`、`run.py`、`config.yaml` — 源码
