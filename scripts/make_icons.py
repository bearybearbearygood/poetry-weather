#!/usr/bin/env python3
"""内容工坊卡片图标 —— 印章风格

设计思路（参照用户提供的参考图）：
  单看「诗」字，读不出天气；单看太阳云雨，读不出诗句。
  所以用一枚印章把两件事叠在同一张章面上：
  上方是天气（太阳 / 云 / 雨 / 月），下方是「诗」。
  这样一眼就能读出「天气 + 诗」，而不是其中一半。

视觉：米白圆底 + 朱红单色线条，传统印章质感。
  圆底同时解决了一个工程问题——图标在深色卡片和浅色背景上都成立，
  不依赖卡片配色。

输出：100 与 200 两个尺寸（官方文档写 100，实测官方实际用 200）。

用法：python3 scripts/make_icons.py
"""

import math
import os

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "content_studio", "assets", "icons")

SIZES = (100, 200)
SS = 5
S = 200 * SS

SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"

PAPER = (247, 241, 227, 255)     # 宣纸米白
SEAL = (181, 52, 42, 255)        # 朱红


def new_canvas():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 圆形章底
    d.ellipse([S * 0.015, S * 0.015, S * 0.985, S * 0.985], fill=PAPER)
    return img, d


def seal_font(size):
    try:
        return ImageFont.truetype(SONGTI, size, index=0)
    except Exception:
        return ImageFont.load_default()


def draw_frame(d, lw=0.024, pad=0.176):
    """朱红方框"""
    d.rounded_rectangle(
        [S * pad, S * pad, S - S * pad, S - S * pad],
        radius=S * 0.035,
        outline=SEAL,
        width=int(S * lw),
    )


def draw_char(d, text="诗", cx=0.612, cy=0.634, size=0.344):
    font = seal_font(int(S * size))
    d.text((S * cx, S * cy), text, font=font, fill=SEAL, anchor="mm",
           stroke_width=int(S * 0.004), stroke_fill=SEAL)


def draw_sun_rays(d, cx, cy, r_in, r_out, count=8, spread=360, tilt=-90):
    """太阳放射线"""
    step = spread / count if spread >= 360 else spread / (count - 1)
    for i in range(count):
        ang = math.radians(tilt - spread / 2 + step * i + (step / 2 if spread >= 360 else 0))
        x1, y1 = cx + math.cos(ang) * S * r_in, cy + math.sin(ang) * S * r_in
        x2, y2 = cx + math.cos(ang) * S * r_out, cy + math.sin(ang) * S * r_out
        d.line([x1, y1, x2, y2], fill=SEAL, width=int(S * 0.020))


def _box(x1, y1, x2, y2):
    """PIL 的 arc 要求 x1<=x2 且 y1<=y2"""
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def draw_cloud(d, cx, cy, w, flip=False):
    """祥云纹：上凸主弧 + 两端卷尾小弧，细线，不压方框"""
    lw = int(S * 0.013)
    r = w * 0.5

    # 主弧（上凸）
    d.arc(_box(cx - r, cy - r, cx + r, cy + r), 190, 350, fill=SEAL, width=lw)

    tail = w * 0.26
    if not flip:
        # 右侧卷尾向下收
        d.arc(_box(cx + r - tail * 2, cy - tail * 0.2, cx + r, cy + tail * 1.8),
              0, 170, fill=SEAL, width=lw)
        # 左侧起笔
        d.arc(_box(cx - r, cy - tail * 1.0, cx - r + tail * 2, cy + tail * 1.0),
              180, 350, fill=SEAL, width=lw)
    else:
        d.arc(_box(cx - r, cy - tail * 0.2, cx - r + tail * 2, cy + tail * 1.8),
              10, 180, fill=SEAL, width=lw)
        d.arc(_box(cx + r - tail * 2, cy - tail * 1.0, cx + r, cy + tail * 1.0),
              190, 360, fill=SEAL, width=lw)


def export(img, name):
    for size in SIZES:
        img.resize((size, size), Image.LANCZOS).save(
            os.path.join(OUT_DIR, f"{name}_{size}.png"))


# ── 四个变体（对角布局）──
# 天气符号放左上角，「诗」放右下角，形成对角呼应。
# 上下垂直排会让符号像"顶"在字头上，压得慌；对角则是各占一角，互不挤压，
# 中间空出的斜向留白反而是呼吸的地方。
#
# 坐标基准（框内 0.176~0.824）：
#   符号区中心 ≈(0.325, 0.325)，占左上约 1/4 框面
#   「诗」中心 (0.598, 0.638)，字号 0.340

def _cloud_block(d, cx, cy, w, color=SEAL, grow=0.0):
    """实心云块：中间大圆 + 两侧圆 + 底部圆角横条

    grow > 0 时按比例外扩，用来先描一圈纸色边——
    否则朱红云压在朱红月亮上会糊成一块，看不出"云在月前"。
    """
    w = w * (1 + grow)
    r = w * 0.25
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    rl = w * 0.19
    d.ellipse([cx - w * 0.27 - rl, cy - w * 0.02, cx - w * 0.27 + rl, cy + w * 0.36], fill=color)
    rr = w * 0.18
    d.ellipse([cx + w * 0.26 - rr, cy - w * 0.01, cx + w * 0.26 + rr, cy + w * 0.35], fill=color)
    d.rounded_rectangle([cx - w * 0.46, cy + w * 0.12, cx + w * 0.44, cy + w * 0.34],
                        radius=w * 0.11, fill=color)


def icon_sun():
    """F1 晴"""
    img, d = new_canvas()
    draw_frame(d)

    cx, cy, r = S * 0.336, S * 0.336, S * 0.072
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SEAL)
    draw_sun_rays(d, cx, cy, 0.084, 0.110, count=8, spread=360, tilt=0)
    draw_char(d)
    return img


def icon_sun_cloud():
    """F2 多云：太阳偏左上，云压右下"""
    img, d = new_canvas()
    draw_frame(d)

    cx, cy, r = S * 0.298, S * 0.312, S * 0.058
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SEAL)
    draw_sun_rays(d, cx, cy, 0.068, 0.090, count=8, spread=360, tilt=0)

    _cloud_block(d, S * 0.372, S * 0.374, S * 0.245)
    draw_char(d)
    return img


def icon_rain():
    """F3 雨：云在左上，雨丝垂下"""
    img, d = new_canvas()
    draw_frame(d)

    _cloud_block(d, S * 0.344, S * 0.302, S * 0.272)

    for dx in (-0.054, 0.0, 0.054):
        x = S * (0.344 + dx)
        d.line([x + S * 0.012, S * 0.410, x - S * 0.012, S * 0.452],
               fill=SEAL, width=int(S * 0.019))

    draw_char(d)
    return img


def icon_cloud_moon():
    """F4 云遮月：弯月左上，云从右下压上"""
    img, d = new_canvas()
    draw_frame(d)

    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([S * 0.228, S * 0.220, S * 0.396, S * 0.388], fill=255)
    md.ellipse([S * 0.280, S * 0.200, S * 0.448, S * 0.368], fill=0)
    img.paste(SEAL, (0, 0), mask)
    d = ImageDraw.Draw(img)

    _cloud_block(d, S * 0.388, S * 0.366, S * 0.228, color=PAPER, grow=0.085)
    _cloud_block(d, S * 0.388, S * 0.366, S * 0.228, color=SEAL)

    draw_char(d)
    return img


def build_preview(variants):
    cols = len(variants)
    cell_w, card = 210, 170
    pad = 34
    row_h = card + 56
    W = pad * 2 + cell_w * cols
    H = 64 + row_h * 2 + 16

    bg = Image.new("RGB", (W, H), (247, 246, 242))
    d = ImageDraw.Draw(bg)
    title_font = ImageFont.truetype(SONGTI, 25, index=0)
    label_font = ImageFont.truetype(SONGTI, 15, index=0)
    small = ImageFont.truetype(SONGTI, 14, index=0)

    d.text((pad, 14), "印章风格图标（天气 + 诗，一枚章面读出两件事）",
           font=title_font, fill=(28, 28, 28))

    def gradient(top, bottom):
        g = Image.new("RGB", (card, card))
        gd = ImageDraw.Draw(g)
        for y in range(card):
            t = y / (card - 1)
            c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            gd.line([(0, y), (card, y)], fill=c)
        return g

    rows = [
        ("深色卡片", gradient((46, 66, 88), (150, 172, 190))),
        ("浅色卡片", gradient((232, 234, 255), (217, 214, 195))),
    ]

    for r, (label, card_img) in enumerate(rows):
        y0 = 64 + r * row_h
        d.text((pad, y0 - 2), label, font=small, fill=(110, 110, 110))
        for i, (name, img) in enumerate(variants):
            x0 = pad + i * cell_w + (cell_w - card) // 2
            y1 = y0 + 16
            bg.paste(card_img, (x0, y1))
            ic = img.resize((116, 116), Image.LANCZOS)
            bg.paste(ic, (x0 + 12, y1 + 12), ic)
            if r == 0:
                d.text((pad + i * cell_w + (cell_w - 96) // 2, y1 + card + 10),
                       name, font=label_font, fill=(50, 50, 50))

    out = os.path.join(OUT_DIR, "preview.png")
    bg.save(out)
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for old in os.listdir(OUT_DIR):
        if old.endswith(".png"):
            os.remove(os.path.join(OUT_DIR, old))

    variants = [
        ("F1 晴", icon_sun()),
        ("F2 多云", icon_sun_cloud()),
        ("F3 雨", icon_rain()),
        ("F4 云遮月", icon_cloud_moon()),
    ]

    keys = {"F1": "sun", "F2": "sun_cloud", "F3": "rain", "F4": "cloud_moon"}
    for name, img in variants:
        export(img, keys[name.split()[0]])

    print("已生成", len(variants) * len(SIZES), "个 PNG")
    print("预览", build_preview(variants))


if __name__ == "__main__":
    main()
