"""麦当劳单品 / 优惠券 / 套餐目录（受控属性表）。

属性是关系图、检查器、位置语义的根基。domain 表示类别（主食/小食/饮品/甜品/券/套餐），
attributes 里的受控词汇驱动「搭配 / 满减 / 单品券」等关系。

价格与热量是占位示例值（接入麦当劳 MCP 后改由 calculate-price / list-nutrition-foods 拉真实数据）。
emoji / tagline / ingredients 是前端展示用的「示例编辑内容」，不是 MCP 数据，随目录一起可复现。
"""
from .schema import Item

# 券规则：满减阈值/立减金额，或单品券目标与优惠额（占位，接 MCP 后读真实券）
COUPONS = {
    "满30减5券": {"kind": "满减", "threshold": 30.0, "off": 5.0},
    "麦辣鸡腿堡半价券": {"kind": "单品半价", "target": "麦辣鸡腿堡", "off": 9.0},
    "薯条免费券": {"kind": "单品免费", "target": "薯条", "off": 11.5},
}

CATALOG: dict = {
    # ---- 主食 ----
    "巨无霸": Item(
        id="big_mac", name="巨无霸", type="physical", description="经典双层牛肉堡",
        attributes=["主食", "饱腹", "高热量"],
        side_effects=["热量较高"],
        observable_signals=["吃完很饱"],
        domain="主食", price=23.5, calories=530,
        emoji="🍔", tagline="双层牛肉，一口满足",
        ingredients=["双层牛肉饼", "芝士", "生菜", "酸黄瓜", "洋葱", "特调酱", "芝麻面包"],
    ),
    "麦辣鸡腿堡": Item(
        id="spicy_burger", name="麦辣鸡腿堡", type="physical", description="辣味鸡腿堡",
        attributes=["主食", "饱腹", "高热量", "辣"],
        side_effects=["偏辣"],
        observable_signals=["辣味明显"],
        domain="主食", price=18.0, calories=490,
        emoji="🍗", tagline="够辣才够味",
        ingredients=["香辣鸡腿排", "生菜", "面包"],
    ),
    "板烧鸡腿堡": Item(
        id="grilled_burger", name="板烧鸡腿堡", type="physical", description="板烧鸡腿堡",
        attributes=["主食", "饱腹", "高热量"],
        side_effects=["热量较高"],
        observable_signals=["吃完很饱"],
        domain="主食", price=19.0, calories=470,
        emoji="🍔", tagline="现点现做，板烧香",
        ingredients=["板烧鸡腿排", "生菜", "面包"],
    ),
    "麦香鱼": Item(
        id="fish_burger", name="麦香鱼", type="physical", description="麦香鱼堡",
        attributes=["主食", "饱腹", "海鲜"],
        side_effects=["含鱼，过敏者注意"],
        observable_signals=["有鱼肉味"],
        domain="主食", price=16.0, calories=390,
        emoji="🐟", tagline="一口吃到海的味道",
        ingredients=["深海鳕鱼排", "塔塔酱", "生菜", "面包"],
    ),
    # ---- 小食 ----
    "薯条": Item(
        id="fries", name="薯条", type="physical", description="中薯条",
        attributes=["小食", "解馋", "可分享", "高热量"],
        side_effects=["凉了不好吃"],
        observable_signals=["趁热吃脆"],
        domain="小食", price=11.5, calories=298,
        emoji="🍟", tagline="金黄酥脆，趁热",
        ingredients=["土豆", "食用盐", "植物油"],
    ),
    "麦乐鸡": Item(
        id="nuggets", name="麦乐鸡", type="physical", description="麦乐鸡块",
        attributes=["小食", "解馋", "可分享"],
        side_effects=["蘸酱偏咸"],
        observable_signals=["外酥里嫩"],
        domain="小食", price=15.5, calories=280,
        emoji="🍗", tagline="一口一个，蘸酱更香",
        ingredients=["鸡肉", "面包糠", "蘸酱"],
    ),
    "玉米杯": Item(
        id="corn", name="玉米杯", type="physical", description="玉米杯",
        attributes=["小食", "解馋", "低卡", "清爽"],
        side_effects=["份量小"],
        observable_signals=["清甜解腻"],
        domain="小食", price=7.0, calories=120,
        emoji="🌽", tagline="清甜解腻",
        ingredients=["甜玉米粒"],
    ),
    "麦辣鸡翅": Item(
        id="wings", name="麦辣鸡翅", type="physical", description="麦辣鸡翅",
        attributes=["小食", "解馋", "辣"],
        side_effects=["偏辣"],
        observable_signals=["香辣"],
        domain="小食", price=13.0, calories=260,
        emoji="🍗", tagline="香辣过瘾",
        ingredients=["鸡翅", "香辣腌料"],
    ),
    # ---- 饮品 ----
    "可乐": Item(
        id="cola", name="可乐", type="physical", description="中杯可乐",
        attributes=["饮品", "解渴", "含糖"],
        side_effects=["含糖较高"],
        observable_signals=["气泡解渴"],
        domain="饮品", price=8.0, calories=140,
        emoji="🥤", tagline="冰爽解渴",
        ingredients=["碳酸水", "糖浆"],
    ),
    "零度可乐": Item(
        id="cola_zero", name="零度可乐", type="physical", description="零度可乐",
        attributes=["饮品", "解渴", "无糖", "低卡"],
        side_effects=["代糖味"],
        observable_signals=["无糖也解渴"],
        domain="饮品", price=8.0, calories=0,
        emoji="🥤", tagline="零糖也解渴",
        ingredients=["碳酸水", "代糖"],
    ),
    "雪碧": Item(
        id="sprite", name="雪碧", type="physical", description="中杯雪碧",
        attributes=["饮品", "解渴", "含糖"],
        side_effects=["含糖较高"],
        observable_signals=["柠檬味清爽"],
        domain="饮品", price=8.0, calories=130,
        emoji="🥤", tagline="柠檬清爽",
        ingredients=["碳酸水", "柠檬味糖浆"],
    ),
    # ---- 甜品 ----
    "麦旋风": Item(
        id="mcflurry", name="麦旋风", type="physical", description="麦旋风冰淇淋",
        attributes=["甜品", "甜", "解馋", "高热量"],
        side_effects=["偏甜偏凉"],
        observable_signals=["绵密冰凉"],
        domain="甜品", price=12.0, calories=320,
        emoji="🍦", tagline="绵密冰爽",
        ingredients=["冰淇淋", "奥利奥碎"],
    ),
    "苹果派": Item(
        id="apple_pie", name="苹果派", type="physical", description="苹果派",
        attributes=["甜品", "甜", "解馋"],
        side_effects=["偏甜"],
        observable_signals=["外酥内甜"],
        domain="甜品", price=6.0, calories=240,
        emoji="🥧", tagline="外酥内甜",
        ingredients=["苹果馅", "酥皮"],
    ),
    "甜筒": Item(
        id="cone", name="甜筒", type="physical", description="原味甜筒",
        attributes=["甜品", "甜", "小份"],
        side_effects=["易化"],
        observable_signals=["冰凉解馋"],
        domain="甜品", price=3.0, calories=150,
        emoji="🍦", tagline="冰凉解馋",
        ingredients=["冰淇淋", "脆筒"],
    ),
    # ---- 优惠券 ----
    "满30减5券": Item(
        id="coupon_30_5", name="满30减5券", type="capability", description="满 30 减 5",
        attributes=["券", "满减", "满30元"],
        side_effects=["不满门槛用不了"],
        observable_signals=["订单金额下降"],
        domain="券", price=0.0, calories=0,
        emoji="🎟️", tagline="凑满就减",
        ingredients=[],
    ),
    "麦辣鸡腿堡半价券": Item(
        id="coupon_spicy_half", name="麦辣鸡腿堡半价券", type="capability", description="麦辣鸡腿堡半价",
        attributes=["券", "折扣", "单品券", "限麦辣鸡腿堡"],
        side_effects=["仅限麦辣鸡腿堡"],
        observable_signals=["该单品价格减半"],
        domain="券", price=0.0, calories=0,
        emoji="🎟️", tagline="鸡腿堡半价",
        ingredients=[],
    ),
    "薯条免费券": Item(
        id="coupon_fries_free", name="薯条免费券", type="capability", description="薯条免费",
        attributes=["券", "单品券", "限薯条"],
        side_effects=["仅限薯条"],
        observable_signals=["薯条 0 元"],
        domain="券", price=0.0, calories=0,
        emoji="🎟️", tagline="薯条免费",
        ingredients=[],
    ),
    # ---- 套餐（用于「反向分解」：拆成单品，算单买 vs 套餐价差）----
    "巨无霸套餐": Item(
        id="bigmac_meal", name="巨无霸套餐", type="meal", description="巨无霸 + 中薯 + 中可乐",
        attributes=["套餐"],
        constraints=["巨无霸", "薯条", "可乐"],
        side_effects=["份量固定，单品不可随换"],
        observable_signals=["一套能吃饱"],
        domain="套餐", price=43.0, calories=968,
        emoji="🍔", tagline="一套吃饱",
        ingredients=["巨无霸", "中薯条", "中可乐"],
    ),
    "麦辣鸡腿堡套餐": Item(
        id="spicy_meal", name="麦辣鸡腿堡套餐", type="meal", description="麦辣鸡腿堡 + 中薯 + 中可乐",
        attributes=["套餐"],
        constraints=["麦辣鸡腿堡", "薯条", "可乐"],
        side_effects=["份量固定"],
        observable_signals=["一套能吃饱"],
        domain="套餐", price=37.5, calories=928,
        emoji="🍗", tagline="辣味一套",
        ingredients=["麦辣鸡腿堡", "中薯条", "中可乐"],
    ),
}
