#!/usr/bin/env python3
"""内容工坊卡片配色模拟

图标定稿为 F1（米白圆底 + 朱红方框 + 太阳 + 诗）。
这里模拟它在不同卡片渐变上的实际观感，用于确定 cardColors 与 textColor。

卡片结构参考内容工坊现有内容：方形卡片，图标在左上角，下方是名称与描述。

用法：python3 scripts/make_card_mock.py
"""

import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON = os.path.join(ROOT, "content_studio", "assets", "icons", "sun_200.png")
OUT = os.path.join(ROOT, "content_studio", "assets", "card_mock.png")

SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"

CARD = 260
GAP = 26
PAD = 34

# (名称, 顶部色, 底部色, 文字色)
SCHEMES = [
    ("A 墨石", (44, 42, 40), (107, 102, 94), (247, 241, 227)),
    ("B 天青", (47, 72, 88), (124, 156, 171), (247, 241, 227)),
    ("C 朱赭", (92, 43, 36), (166, 107, 92), (247, 241, 227)),
]


def gradient(w, h, top, bottom):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=c)
    return img


def main():
    n = len(SCHEMES)
    W = PAD * 2 + CARD * n + GAP * (n - 1)
    H = PAD + 44 + CARD + 40

    bg = Image.new("RGB", (W, H), (247, 246, 242))
    d = ImageDraw.Draw(bg)

    title = ImageFont.truetype(SONGTI, 24, index=0)
    name_f = ImageFont.truetype(SONGTI, 20, index=0)
    desc_f = ImageFont.truetype(SONGTI, 14, index=0)
    tag_f = ImageFont.truetype(SONGTI, 15, index=0)

    d.text((PAD, 12), "内容工坊卡片配色模拟（图标 F1）", font=title, fill=(28, 28, 28))

    icon_full = Image.open(ICON).convert("RGBA")
    icon_small = icon_full.resize((56, 56), Image.LANCZOS)

    for i, (label, top, bottom, text_color) in enumerate(SCHEMES):
        x0 = PAD + i * (CARD + GAP)
        y0 = PAD + 44

        card = gradient(CARD, CARD, top, bottom)
        bg.paste(card, (x0, y0))

        # 图标
        bg.paste(icon_small, (x0 + 20, y0 + 20), icon_small)

        # 名称
        d.text((x0 + 20, y0 + 158), "诗词天气", font=name_f, fill=text_color)
        # 描述
        d.text((x0 + 20, y0 + 192), "看天气，也读一句诗。", font=desc_f,
               fill=(text_color[0], text_color[1], text_color[2]))
        d.text((x0 + 20, y0 + 212), "按当地天气每日匹配应景古诗。", font=desc_f,
               fill=(text_color[0], text_color[1], text_color[2]))

        # 色值标注
        d.text((x0 + 20, y0 + CARD + 8),
               "%s  #%02X%02X%02X → #%02X%02X%02X" % (label, *top, *bottom),
               font=tag_f, fill=(90, 90, 90))

    bg.save(OUT)
    print("已生成", OUT)


if __name__ == "__main__":
    main()
