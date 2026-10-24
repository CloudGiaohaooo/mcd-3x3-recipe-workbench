"""生成麦门 3×3 的 Q 版 2D 像素图（web/sprites/*.png）。

纯标准库（zlib + struct 手写 PNG），不依赖 Pillow，保证可复现。
每个素材是 16×16 的像素画，按 SCALE 放大成 64×64 的 PNG（最近邻，保持像素感）。

用法：
    python tools/gen_sprites.py
生成：
    web/sprites/<id>.png     每个单品 / 券 / 套餐一张
    web/sprites/sprites.png  总览图（供 README 图鉴 / 本脚本自检）
"""
import os
import struct
import zlib

SCALE = 4
SIZE = 16

# 调色板：字符 -> RGBA
PAL = {
    ".": None,              # 透明
    "K": (43, 33, 26, 255),     # 描边（暖黑）
    "W": (255, 255, 255, 255),  # 白
    "Y": (255, 199, 44, 255),   # 麦当劳黄
    "D": (218, 41, 28, 255),    # 麦当劳红
    "O": (245, 166, 35, 255),   # 橙（炸物 / 火焰）
    "B": (224, 164, 94, 255),   # 面包浅棕
    "N": (138, 82, 35, 255),    # 深棕（肉饼 / 炸鸡 / 酥皮）
    "S": (255, 227, 194, 255),  # 奶白
    "P": (244, 168, 192, 255),  # 腮红粉
    "G": (62, 155, 79, 255),    # 生菜绿
    "L": (168, 212, 107, 255),  # 浅绿（柠檬 / 青柠）
    "C": (255, 210, 63, 255),   # 芝士黄
    "M": (232, 165, 0, 255),    # 芥末 / 焦糖黄
    "U": (46, 134, 222, 255),   # 蓝
    "A": (122, 199, 234, 255),  # 浅蓝（零度 / 冰）
    "E": (62, 42, 26, 255),     # 可乐深棕
    "H": (107, 66, 38, 255),    # 巧克力 / 奥利奥
    "T": (209, 59, 59, 255),    # 番茄红
    "F": (79, 163, 184, 255),   # 鱼 / 海洋青
    "V": (142, 68, 173, 255),   # 紫（券）
    "X": (154, 143, 134, 255),  # 灰（托盘 / 银）
    "I": (255, 243, 224, 255),  # 冰淇淋奶白
}


def _row(bg, n=8):
    """汉堡 / 杯体的一行：左右描边 + n 个背景色。"""
    return "...K" + bg * n + "K..."


def _eyes(bg, eye="K", glint="W"):
    """Q 版表情两行（眼睛），8 格内居中，左右眼各 2 宽。"""
    e1 = "...K" + bg + glint + eye + bg * 2 + glint + eye + bg + "K..."
    e2 = "...K" + bg + eye + eye + bg * 2 + eye + eye + bg + "K..."
    return e1, e2


def _mouth(bg):
    """腮红 + 小嘴一行。"""
    return "...KP" + bg * 2 + "KK" + bg * 2 + "PK..."


def _eyes_light(bg):
    """深色底用的白眼睛（2 行）。"""
    return ("...K" + bg + "WW" + bg * 2 + "WW" + bg + "K...",
            "...K" + bg + "WW" + bg * 2 + "WW" + bg + "K...")


def _mouth_light(bg):
    """深色底用的白嘴 + 腮红。"""
    return "...KP" + bg * 2 + "WW" + bg * 2 + "PK..."


def _burger(top, layers, bottom="B", light_face=False):
    """四层汉堡（顶层=面包/调味色，4 层夹心，底部面包）。"""
    eyes = _eyes_light(top) if light_face else _eyes(top)
    mouth = _mouth_light(top) if light_face else _mouth(top)
    return [
        ".....KKKKKK.....",
        "....KKKKKKKK....",
        "...KKKKKKKKKK...",
        _row(top),
        _row(top),
        eyes[0],
        eyes[1],
        mouth,
        _row(top),
        _row(layers[0]),
        _row(layers[1]),
        _row(layers[2]),
        _row(layers[3]),
        _row(bottom),
        "...KKKKKKKKKK...",
        "................",
    ]


def _cup(cup, liquid, straw="Y", label="W"):
    """带吸管的杯：顶部露出液体，白色标签带放表情，杯身有品牌色。"""
    return [
        "................",
        ".........." + straw + ".....",
        ".........." + straw + ".....",
        "...KKKKKKKKKK...",
        _row(liquid),
        _row(liquid),
        _eyes(label)[0],
        _eyes(label)[1],
        _mouth(label),
        _row(label),
        _row(cup),
        _row(cup),
        _row(cup),
        _row(cup),
        "...KKKKKKKKKK...",
        "................",
    ]


def _ticket(body, glyph, glyph_cols=3):
    """优惠券：圆角矩形 + 中央 3 宽符号。glyph 为 5 行字符串。"""
    rows = ["................"] * SIZE
    for rr in range(3, 13):
        rows[rr] = ".K" + body * 12 + "K."
    left = 6
    for i, g in enumerate(glyph):
        rr = 6 + i
        line = list(rows[rr])
        for j in range(glyph_cols):
            line[left + j] = body if g[j] == "." else g[j]
        rows[rr] = "".join(line)
    return rows


# ---- 符号（3×5 像素字）----
D5 = ["DDD", "D..", "DDD", "..D", "DDD"]
D0 = [".D.", "D.D", "D.D", "D.D", ".D."]
PCT = ["D.D", "..D", ".D.", "D..", "D.D"]


def _meal(burger_top):
    """套餐托盘：汉堡 + 薯条 + 饮料，下面一条托盘。"""
    g = [["."] * 16 for _ in range(16)]

    def put(x, y, ch):
        g[y][x] = ch

    # 汉堡（列 1–5，行 6–11）
    for x in (2, 3, 4):
        put(x, 6, "K")
    for y in (7, 8):
        put(1, y, "K"); put(5, y, "K")
        for x in (2, 3, 4):
            put(x, y, burger_top)
    for y in (9, 10):
        put(1, y, "K"); put(5, y, "K")
        for x in (2, 3, 4):
            put(x, y, "N")
    for x in range(1, 6):
        put(x, 11, "K")

    # 薯条（列 7–11，行 6–12）
    for y in (6, 7, 8):
        put(8, y, "Y"); put(9, y, "Y")
    for x in range(7, 12):
        put(x, 9, "K")
    for y in (10, 11):
        put(7, y, "K"); put(11, y, "K")
        for x in (8, 9, 10):
            put(x, y, "D")
    for x in range(7, 12):
        put(x, 12, "K")

    # 饮料（列 13–15，行 6–12）
    put(14, 6, "Y")
    for x in range(13, 16):
        put(x, 7, "K")
    for y in (8, 9, 10, 11):
        put(13, y, "K"); put(15, y, "K"); put(14, y, "D")
    for x in range(13, 16):
        put(x, 12, "K")

    # 托盘
    for x in range(16):
        put(x, 13, "X")

    return ["".join(row) for row in g]


SPRITES = {
    # ---- 主食 ----
    "big_mac": _burger("B", ["G", "N", "C", "N"]),
    "spicy_burger": _burger("D", ["G", "N", "C", "N"], light_face=True),
    "grilled_burger": _burger("O", ["G", "N", "C", "N"]),
    "fish_burger": _burger("B", ["G", "F", "C", "N"]),
    # ---- 小食 ----
    "fries": [
        "................",
        "....YY..YY......",
        "...YYY..YYY.....",
        "...YYY..YYY.....",
        "....YY..YY......",
        "....YY..YY......",
        "...KKKKKKKKKK...",
        "...KDDDDDDDDK...",
        "...KDWWDDWWDK...",
        "...KDWWDDWWDK...",
        "...KPDDWWWDPK...",
        "...KDDDDDDDDK...",
        "...KDDDDDDDDK...",
        "...KKKKKKKKKK...",
        "................",
        "................",
    ],
    "nuggets": [
        "................",
        "................",
        ".....KKKKKK.....",
        "....KOOOOOOK....",
        "...KOOOOOOOOK...",
        "...KOOOOOOOOK...",
        _eyes("O")[0],
        _eyes("O")[1],
        _mouth("O"),
        "...KOOOOOOOOK...",
        "...KOOOOOOOOK...",
        "...KOOOOOOOOK...",
        "....KOOOOOOK....",
        ".....KKKKKK.....",
        "................",
        "................",
    ],
    "corn": [
        "................",
        "......GG........",
        ".....GGGG.......",
        "...KKKKKKKKKK...",
        "...KYYYYYYYYK...",
        "...KYYYYYYYYK...",
        _eyes("Y")[0],
        _eyes("Y")[1],
        _mouth("Y"),
        "...KYYYYYYYYK...",
        "...KYYYYYYYYK...",
        "...KYYYYYYYYK...",
        "...KYYYYYYYYK...",
        "...KKKKKKKKKK...",
        "................",
        "................",
    ],
    "wings": [
        "................",
        "................",
        ".....KKKKK......",
        "....KNNNNNK.....",
        "...KNNNNNNNK....",
        "...KNNNNNNNK....",
        _eyes_light("N")[0],
        _eyes_light("N")[1],
        _mouth_light("N"),
        "...KNNNNNNNK....",
        "...KNNNNNNNK....",
        "....KNNNNNK.....",
        "....KWWWWWK.....",
        ".....KKKKK......",
        "................",
        "................",
    ],
    # ---- 饮品 ----
    "cola": _cup("D", "E"),
    "cola_zero": _cup("E", "A", straw="W"),
    "sprite": _cup("G", "L"),
    # ---- 甜品 ----
    "mcflurry": [
        "................",
        "................",
        ".....IIIII......",
        "....IWIWIIWI....",
        "...KIIIIIIIIK...",
        "...KIIIIIIIIK...",
        "...KIWIIIIWIK...",
        "...KIWIIIIWIK...",
        "...KPIIIKKIIPK..",
        "...KIIIIIIIIK...",
        "...KKKKKKKKKK...",
        "...KYYYYYYYYK...",
        "...KYYYYYYYYK...",
        "...KKKKKKKKKK...",
        "................",
        "................",
    ],
    "apple_pie": [
        "................",
        "................",
        ".....KKKKKK.....",
        "....KNNNNNNK....",
        "...KNNNNNNNNK...",
        _eyes_light("N")[0],
        _eyes_light("N")[1],
        _mouth_light("N"),
        "...KNNNNNNNNK...",
        "...KNNNNNNNNK...",
        "...KNNNNNNNNK...",
        "...KNNNNNNNNK...",
        "....KNNNNNNK....",
        ".....KKKKKK.....",
        "................",
        "................",
    ],
    "cone": [
        "................",
        "................",
        ".....IIIII......",
        "....IWIWIIWI....",
        "...IIIIIIIIII...",
        "...IIIIIIIIII...",
        "...IIIIIIIIII...",
        "....KKKKKKKK....",
        ".....KNNNNK.....",
        "......KNNK......",
        ".......KNK......",
        "........K.......",
        "................",
        "................",
        "................",
        "................",
    ],
    # ---- 优惠券 ----
    "coupon_30_5": _ticket("Y", D5),
    "coupon_spicy_half": _ticket("V", PCT),
    "coupon_fries_free": _ticket("Y", D0),
    # ---- 套餐 ----
    "bigmac_meal": _meal("B"),
    "spicy_meal": _meal("D"),
}

# 套餐（spicy）顶部加一点火焰感
SPRITES["spicy_burger"][0] = ".......OO......."

# 半价券符号用白（紫底更醒目）
SPRITES["coupon_spicy_half"] = _ticket("V", ["WWW", "..W", ".W.", "W..", "WWW"])
# 免费券符号用绿（0 元）
SPRITES["coupon_fries_free"] = _ticket("Y", [".G.", "G.G", "G.G", "G.G", ".G."])

ORDER = [
    "big_mac", "spicy_burger", "grilled_burger", "fish_burger",
    "fries", "nuggets", "corn", "wings",
    "cola", "cola_zero", "sprite",
    "mcflurry", "apple_pie", "cone",
    "coupon_30_5", "coupon_spicy_half", "coupon_fries_free",
    "bigmac_meal", "spicy_meal",
]


def _chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    c += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return c


def _png_bytes(rows_rgba):
    """rows_rgba: SIZE 行 × SIZE 列，每格 (r,g,b,a) 或 None。"""
    h = len(rows_rgba)
    w = len(rows_rgba[0])
    raw = bytearray()
    for row in rows_rgba:
        raw.append(0)  # filter none
        for px in row:
            raw += bytes(px if px else (0, 0, 0, 0))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


def render(sprite):
    """16×16 字符画 -> 64×64 RGBA 行。"""
    if len(sprite) != SIZE or any(len(r) != SIZE for r in sprite):
        raise ValueError("sprite 必须是 %d 行 × %d 列" % (SIZE, SIZE))
    big = []
    for r in range(SIZE):
        src = sprite[r]
        for _ in range(SCALE):
            row = []
            for c in range(SIZE):
                px = PAL.get(src[c])
                row += [px] * SCALE
            big.append(row)
    return big


def _blank(w, h, color):
    return [[color] * w for _ in range(h)]


def make_sheet():
    """总览图：每张 64 内嵌 + 8 间隙，奶白背景。"""
    pad, gap, cell = 12, 8, SIZE * SCALE
    cols = 5
    rows = (len(ORDER) + cols - 1) // cols
    W = pad * 2 + cols * cell + (cols - 1) * gap
    H = pad * 2 + rows * cell + (rows - 1) * gap
    bg = (250, 246, 239, 255)
    sheet = _blank(W, H, bg)
    for i, name in enumerate(ORDER):
        img = render(SPRITES[name])
        x0 = pad + (i % cols) * (cell + gap)
        y0 = pad + (i // cols) * (cell + gap)
        for dy in range(cell):
            for dx in range(cell):
                px = img[dy][dx]
                if px and px[3]:
                    sheet[y0 + dy][x0 + dx] = px
    return sheet


def main():
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "sprites")
    os.makedirs(root, exist_ok=True)
    for name in ORDER:
        with open(os.path.join(root, name + ".png"), "wb") as f:
            f.write(_png_bytes(render(SPRITES[name])))
    with open(os.path.join(root, "sprites.png"), "wb") as f:
        f.write(_png_bytes(make_sheet()))
    print("已生成 %d 张素材 + 总览图 -> %s" % (len(ORDER), root))


if __name__ == "__main__":
    main()
