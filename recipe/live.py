"""实时数据层：把麦当劳 MCP 的真实菜单/营养/券/套餐构成，灌进离线目录。

离线目录（catalog.py）是「示例占位」，本模块负责在 --live 模式下：
1. query-nearby-stores    解析一家营业中的门店（storeCode）
2. query-meals            拉真实菜单，用名称别名把目录单品价替换成真实价（元）
3. list-nutrition-foods   拉真实营养表，best-effort 替换热量（未匹配保留占位值）
4. query-meal-detail      拉套餐真实构成，替换套餐 constraints 与价
5. query-store-coupons    拉门店可用券（真实券只有 couponId）
6. calculate-price        真实计价（验证一个示例组合，单位「分」→ 元）

离线可复现（无 token / 无网络时回退静态目录），真实模式全走 MCP。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .mcp_client import McpClient, McpError, cents_to_yuan, parse_nutrition

# 目录单品名 -> 真实菜单里的名字（价格来源）
MENU_ALIAS = {
    "巨无霸": "巨无霸",
    "麦辣鸡腿堡": "麦辣鸡腿汉堡",
    "板烧鸡腿堡": "板烧鸡腿堡",
    "麦香鱼": "麦香鱼",
    "薯条": "薯条",
    "麦乐鸡": "麦乐鸡",
    "玉米杯": "玉米杯",
    "麦辣鸡翅": "麦辣鸡翅",
    "可乐": "可乐",
    "零度可乐": "无糖可乐",
    "雪碧": "雪碧",
    "麦旋风": "经典麦旋风",
    "苹果派": "派",
    "甜筒": "圆筒冰淇淋",
    "巨无霸套餐": "巨无霸三件套",
    "麦辣鸡腿堡套餐": "麦辣鸡腿汉堡三件套",
}

# 目录套餐名 -> 真实菜单套餐名（用于 query-meal-detail 拆构成）
MEAL_ALIAS = {
    "巨无霸套餐": "巨无霸三件套",
    "麦辣鸡腿堡套餐": "麦辣鸡腿汉堡三件套",
}

# 套餐构成里的真实单品名 -> 目录单品名（用于回填套餐 constraints）
COMPONENT_ALIAS = {
    "巨无霸": "巨无霸",
    "新升级巨无霸": "巨无霸",
    "麦辣鸡腿汉堡": "麦辣鸡腿堡",
    "麦辣鸡腿堡": "麦辣鸡腿堡",
    "中薯条": "薯条",
    "大薯条": "薯条",
    "薯条": "薯条",
    "脆脆薯条": "薯条",
    "可乐中杯": "可乐",
    "可乐": "可乐",
    "小杯玉米杯": "玉米杯",
    "大杯玉米杯": "玉米杯",
    "玉米杯": "玉米杯",
}

# 目录单品名 -> 营养表里的名字（best-effort 热量，未匹配保留占位）
NUTRITION_ALIAS = {
    "薯条": "中薯条",
    "甜筒": "圆筒冰淇淋",
    "麦乐鸡": "麦乐鸡5块",
    "玉米杯": "小杯玉米杯",
    "麦辣鸡翅": "麦辣鸡翅-2块",
    "苹果派": "香芋派",
}


class LiveData:
    """一次 --live 拉取的全部真实数据 + 对目录的修改摘要。"""

    def __init__(self):
        self.store: Dict[str, Any] = {}
        self.menu_codes: Dict[str, str] = {}       # 目录名 -> 真实餐品 code
        self.menu_prices: Dict[str, float] = {}    # 目录名 -> 真实价（元）
        self.nutrition_kcal: Dict[str, int] = {}   # 目录名 -> 真实热量
        self.coupons: List[Dict[str, Any]] = []    # 门店可用券（含 couponId）
        self.meal_components: Dict[str, List[str]] = {}  # 套餐目录名 -> 真实构成单品目录名
        self.price_check: Dict[str, Any] = {}      # calculate-price 示例结果
        self.errors: List[str] = []                # 非致命降级说明

    def summary(self) -> str:
        s = self.store.get("storeName", "未知门店")
        addr = self.store.get("address", "")
        return f"{s}（{addr}）code={self.store.get('storeCode', '-')}"


def _first_open_store(data) -> Optional[Dict[str, Any]]:
    stores = data.get("data") or []
    # 优先营业中的；全关则退回第一家
    for st in stores:
        if st.get("businessStatus"):
            return st
    return stores[0] if stores else None


def fetch_live(client: McpClient, city: str, keyword: str) -> LiveData:
    """调用 6 个 MCP 工具，组装 LiveData。失败项降级并记录，不中断。"""
    live = LiveData()

    # 1. 门店
    try:
        st = _first_open_store(client.nearby_stores(city, keyword))
        if not st:
            live.errors.append("附近没有门店（query-nearby-stores 返回空）")
            return live
        live.store = st
    except McpError as exc:
        live.errors.append("门店解析失败：%s" % exc)
        return live

    store_code = str(st.get("storeCode", ""))

    # 2. 菜单 → 名称/价/code
    try:
        menu = client.menu(store_code)
        meals = (menu.get("data") or {}).get("meals") or {}
        # 建「真实菜单名 -> (code, 价元)」反查
        by_name: Dict[str, Dict[str, Any]] = {}
        for code, v in meals.items():
            name = (v or {}).get("name")
            if name:
                by_name[name] = {"code": code, "price": float(v.get("currentPrice") or 0)}
        for cat_name, real_name in MENU_ALIAS.items():
            hit = by_name.get(real_name)
            if hit:
                live.menu_codes[cat_name] = hit["code"]
                live.menu_prices[cat_name] = hit["price"]
    except McpError as exc:
        live.errors.append("菜单拉取失败：%s" % exc)

    # 3. 营养表 → 热量
    try:
        nut = client.nutrition()
        kcal_by_name = parse_nutrition(nut.get("data") if isinstance(nut, dict) else nut)
        for cat_name, real_name in NUTRITION_ALIAS.items():
            if real_name in kcal_by_name:
                live.nutrition_kcal[cat_name] = kcal_by_name[real_name]
    except McpError as exc:
        live.errors.append("营养表拉取失败：%s" % exc)

    # 4. 套餐构成（query-meal-detail）
    for cat_meal, real_meal in MEAL_ALIAS.items():
        code = live.menu_codes.get(cat_meal)
        if not code:
            continue
        try:
            detail = client.meal_detail(store_code, code)
            comps: List[str] = []
            for rnd in (detail.get("data") or {}).get("rounds") or []:
                for ch in rnd.get("choices") or []:
                    if ch.get("isDefault") == 1 and ch.get("name"):
                        mapped = COMPONENT_ALIAS.get(ch["name"])
                        if mapped and mapped not in comps:
                            comps.append(mapped)
            if comps:
                live.meal_components[cat_meal] = comps
        except McpError as exc:
            live.errors.append("套餐构成拉取失败（%s）：%s" % (cat_meal, exc))

    # 5. 门店券（真实券只有 query-store-coupons 返回 couponId）
    try:
        live.coupons = (client.store_coupons(store_code).get("data") or []) or []
    except McpError as exc:
        live.errors.append("券拉取失败：%s" % exc)

    # 6. 真实计价验证：巨无霸 + 薯条 + 可乐（若都能映射到 code）
    try:
        codes = [live.menu_codes.get(n) for n in ("巨无霸", "薯条", "可乐")]
        if all(codes):
            items = [{"productCode": c, "quantity": 1} for c in codes]
            price = client.calculate_price(store_code, items)
            data = price.get("data") or {}
            live.price_check = {
                "items": [("巨无霸", "薯条", "可乐")],
                "price_yuan": cents_to_yuan(data.get("price", 0)),
                "list": data.get("productList") or [],
            }
    except McpError as exc:
        live.errors.append("真实计价验证失败：%s" % exc)

    return live


def enrich_catalog(catalog: Dict[str, Any], live: LiveData) -> List[str]:
    """把 live 数据写回目录（原地改 Item.price/calories/constraints），返回改动摘要。"""
    notes: List[str] = []
    for name, price in live.menu_prices.items():
        item = catalog.get(name)
        if item is None:
            continue
        old = item.price
        item.price = price
        code = live.menu_codes.get(name, "")
        notes.append(f"价格：{name} ¥{old} → ¥{price}（code={code}）")
    for name, kcal in live.nutrition_kcal.items():
        item = catalog.get(name)
        if item is None:
            continue
        old = item.calories
        item.calories = kcal
        notes.append(f"热量：{name} {old} → {kcal} kcal")
    for meal, comps in live.meal_components.items():
        item = catalog.get(meal)
        if item is None:
            continue
        old = list(item.constraints)
        item.constraints = comps
        # 套餐价以菜单里的套餐现价为准（menu_prices 已含）
        notes.append(f"构成：{meal} {old} → {comps}")
    return notes
