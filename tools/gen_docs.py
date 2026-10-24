"""生成 README 用演示图（需本机 Chrome + Pillow，非运行时依赖）。

前置：先起网页服务  python web.py --port 8765
用法：  python tools/gen_docs.py

产出 docs/：
    demo.png          正向合成（巨无霸薯条可乐）
    demo_position.png 主辅反转（可乐主推）
    demo_decompose.png反向分解（巨无霸 → 原料/卖点/营养）
    demo_afternoon.png下午茶（麦旋风可乐苹果派）
    demo.gif          上面 4 帧拼成的动画
    sprites.png       全部元素像素图图鉴（带名称标签）
"""
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
SPRITES = os.path.join(ROOT, "web", "sprites")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE = "http://127.0.0.1:8765"

PRESETS = [
    ("demo", "巨无霸薯条可乐"),
    ("demo_position", "可乐主推反转"),
    ("demo_decompose", "decompose:巨无霸"),
    ("demo_afternoon", "麦旋风下午茶"),
]

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]


def find_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def chrome_shot(url, out, width=1280, height=900, budget=6000):
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
         f"--window-size={width},{height}",
         f"--virtual-time-budget={budget}",
         f"--screenshot={out}", url],
        check=True, capture_output=True,
    )


def make_gif(frames, out, width=800):
    imgs = [Image.open(f).convert("RGB") for f in frames]
    w = width
    scaled = []
    for im in imgs:
        h = int(im.height * w / im.width)
        scaled.append(im.resize((w, h), Image.LANCZOS))
    scaled[0].save(out, save_all=True, append_images=scaled[1:],
                   duration=1600, loop=0, optimize=True)


def sprite_gallery(out):
    font_path = find_font()
    font = ImageFont.truetype(font_path, 18) if font_path else ImageFont.load_default()
    names = [
        ("big_mac", "巨无霸"), ("spicy_burger", "麦辣鸡腿堡"),
        ("grilled_burger", "板烧鸡腿堡"), ("fish_burger", "麦香鱼"),
        ("fries", "薯条"), ("nuggets", "麦乐鸡"), ("corn", "玉米杯"),
        ("wings", "麦辣鸡翅"), ("cola", "可乐"), ("cola_zero", "零度可乐"),
        ("sprite", "雪碧"), ("mcflurry", "麦旋风"), ("apple_pie", "苹果派"),
        ("cone", "甜筒"), ("coupon_30_5", "满30减5券"),
        ("coupon_spicy_half", "半价券"), ("coupon_fries_free", "薯条免费券"),
        ("bigmac_meal", "巨无霸套餐"), ("spicy_meal", "麦辣套餐"),
    ]
    cell, gap, pad, label_h = 84, 14, 20, 26
    cols = 5
    rows = (len(names) + cols - 1) // cols
    W = pad * 2 + cols * cell + (cols - 1) * gap
    H = pad * 2 + rows * (cell + label_h) + (rows - 1) * gap
    bg = Image.new("RGB", (W, H), (250, 246, 239))
    draw = ImageDraw.Draw(bg)
    for i, (sid, label) in enumerate(names):
        x0 = pad + (i % cols) * (cell + gap)
        y0 = pad + (i // cols) * (cell + label_h + gap)
        sp = Image.open(os.path.join(SPRITES, sid + ".png")).convert("RGBA")
        sp = sp.resize((64, 64), Image.NEAREST)
        bg.paste(sp, (x0 + (cell - 64) // 2, y0 + (cell - 64) // 2), sp)
        tw = draw.textlength(label, font=font)
        draw.text((x0 + (cell - tw) // 2, y0 + cell + 4), label,
                  font=font, fill=(74, 64, 54))
    bg.save(out)


def main():
    os.makedirs(DOCS, exist_ok=True)
    tmp = []
    for name, preset in PRESETS:
        out = os.path.join(DOCS, name + ".png")
        chrome_shot(f"{BASE}/?preset={preset}", out)
        tmp.append(out)
        print("截图", name)
    make_gif(tmp, os.path.join(DOCS, "demo.gif"))
    print("生成 demo.gif")
    sprite_gallery(os.path.join(DOCS, "sprites.png"))
    print("生成 sprites.png ->", os.path.join(DOCS, "sprites.png"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
