# MCP 接入说明 · MCP_INTEGRATION

本项目 **真实调用麦当劳 MCP**，把真实菜单 / 营养 / 优惠券 / 套餐构成 / 计价灌进「麦门 3×3 配方工作台」的合成与分解流水线。

## 使用的 MCP Server 与工具

| 工具 | 用途 | 项目里的落点 |
| --- | --- | --- |
| `query-nearby-stores` | 定位一家营业中的门店，拿到 `storeCode` | `recipe/live.py::fetch_live` |
| `query-meals` | 拉门店真实菜单（餐品名 / code / 现价） | 回填目录单品价、套餐价 |
| `list-nutrition-foods` | 拉全量营养表（热量 kcal 等） | best-effort 回填目录热量 |
| `query-meal-detail` | 拉套餐真实构成（主食 / 小食 / 饮料的默认项与替换项） | 回填套餐 `constraints` 与价 |
| `query-store-coupons` | 拉门店可用券（只有这里返回 `couponId`） | 展示真实券 + 券后价链路 |
| `calculate-price` | 真实计价（含券），返回单位为「分」 | 合成/分解的真实价与「省多少」 |

协议：Streamable HTTP + JSON-RPC 2.0，Bearer Token 鉴权（`https://mcp.mcd.cn`，protocolVersion 2025-03-26）。

## 调用流程

```
query-nearby-stores(city, keyword)
   └─ 选 businessStatus=true 的门店 → storeCode
        ├─ query-meals(storeCode) → categories + meals{code: name/currentPrice}
        ├─ list-nutrition-foods()   → 160 条营养文本表 → {食物名: kcal}
        ├─ query-meal-detail(code)  → rounds[].choices[] → 套餐构成
        ├─ query-store-coupons(storeCode) → data[]（含 couponId）
        └─ calculate-price(storeCode, items) → 分 → 元（真实计价验证）
```

结果回填 `recipe/catalog.py` 的 `Item.price / Item.calories / Item.constraints`，之后跑的是**同一套**领域无关的合成 / 检查 / 打分流水线。

## 关键约定（避免踩坑）

- **单位**：`query-meals` 的 `currentPrice` 是**元**（字符串）；`calculate-price` 的 `price` / `subtotal` 是**分**（除以 100）。见 `mcp_client.cents_to_yuan`。
- **门店营业状态**：`query-nearby-stores` 返回的 `businessStatus=false` 门店不能拉菜单（会报「门店已关闭」），代码优先选营业中的门店。
- **券只有门店接口有 `couponId`**：`calculate-price` 的 `items[].couponId/couponCode` 只能从 `query-store-coupons` 拿到；菜单接口不返回券。
- **营养表是文本**：`list-nutrition-foods` 的 `data` 是 `[160]{字段}:\n 名称,...` 文本，用 `mcp_client.parse_nutrition` 解析。
- **不虚构折扣**：麦当劳没有固定折扣，`recipe/templates.py` 的 `_combo_of` 命中目录套餐才取套餐价，否则按单点总价；「省 ¥X」只在真实价差 > 0 时才出现。

## 运行方式

```bash
# 1. 设置 Token（只放环境变量，绝不写进代码/提交文件）
#    Windows:  set MCD_MCP_TOKEN=<你的Token>
#    macOS/Linux: export MCD_MCP_TOKEN=<你的Token>

# 2. 实时模式：拉真实数据后跑流水线
python run.py --live --demo                    # 全部示例（真实价）
python run.py --live --scenario 巨无霸薯条可乐
python run.py --live --decompose 麦辣鸡腿堡套餐  # 真实套餐拆解 + 价差
python run.py --live --city 上海市 --keyword 外滩  # 换城市/门店

# 3. 无 Token 时离线可复现（占位价，卡上标注「示例占位值」）
python run.py --demo
```

Token 只经 `MCD_MCP_TOKEN` 环境变量注入，代码里没有硬编码（见 `recipe/mcp_client.py::McpClient`），也不进入任何会被提交的文件。

## 业务价值

- **合成**：把单品/券摆进 3×3，`_combo_of` 用真实套餐价判断「命中套餐 vs 按单点」，只报真实价差（例：麦辣鸡腿堡三件套 ¥49 vs 单买 ¥51.5，省 ¥2.5；巨无霸三件套 ¥54.5 与单点同价）。
- **分解**：`query-meal-detail` 拆出套餐真实构成，`calculate-price` 验证「套餐 vs 单点」谁更低。
- **营养**：真实热量随卡片一起出，代替写死的示例值。
