#!/usr/bin/env python3
"""内容工坊上线后的效果示意

画三个位置的样子：
  1. 内容工坊列表里的卡片
  2. 添加时的参数表单（城市输入框）
  3. Quote/0 屏幕上实际显示的内容

注意：设备上的排版是按接口返回的 display 字段示意的，
最终渲染样式由 Dot 侧模板决定，有偏差是正常的。

用法：python3 scripts/make_preview_mock.py
"""

import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON = os.path.join(ROOT, "content_studio", "assets", "icons", "sun_200.png")
OUT = os.path.join(ROOT, "content_studio", "assets", "preview_flow.png")

SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"
NOTO = os.path.join(ROOT, "fonts", "NotoSansCJKsc-Regular.otf")

W, H = 1180, 640
BG = (244, 243, 239)
INK = (28, 28, 30)
GREY = (120, 118, 112)
LIGHT = (206, 203, 196)

CARD_TOP = (46, 44, 42)
CARD_BOT = (110, 105, 96)
CARD_TEXT = (247, 241, 227)


def font(size, path=SONGTI):
    try:
        return ImageFont.truetype(path, size, index=0)
    except Exception:
        return ImageFont.load_default()


def paste_rounded(bg, img, xy, radius):
    """带圆角遮罩的粘贴，避免透明区被当成黑色"""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, img.size[0] - 1, img.size[1] - 1], radius=radius, fill=255)
    bg.paste(img, xy, mask)


def gradient(w, h, top, bottom):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=c)
    return img


def draw_card(bg, x, y, w, h):
    """① 内容工坊列表里的卡片"""
    paste_rounded(bg, gradient(w, h, CARD_TOP, CARD_BOT), (x, y), 18)

    icon = Image.open(ICON).convert("RGBA").resize((54, 54), Image.LANCZOS)
    bg.paste(icon, (x + 18, y + 18), icon)

    d = ImageDraw.Draw(bg)
    d.text((x + 18, y + h - 78), "诗词天气", font=font(22), fill=CARD_TEXT)
    d.text((x + 18, y + h - 46), "看天气，也读一句诗。", font=font(13, NOTO),
           fill=(224, 218, 203))

    # 分类角标
    tag_w, tag_h = 52, 24
    tx, ty = x + w - tag_w - 16, y + 16
    d.rounded_rectangle([tx, ty, tx + tag_w, ty + tag_h], radius=12,
                        outline=(255, 255, 255), width=1)
    d.text((tx + tag_w / 2, ty + tag_h / 2), "天气", font=font(13, NOTO),
           fill=CARD_TEXT, anchor="mm")


def draw_form(bg, x, y, w, h):
    """② 添加时的参数表单"""
    paste_rounded(bg, Image.new("RGB", (w, h), (252, 251, 249)), (x, y), 18)
    d = ImageDraw.Draw(bg)

    d.text((x + 22, y + 20), "添加内容", font=font(19), fill=INK)
    d.text((x + 22, y + 56), "城市", font=font(14, NOTO), fill=GREY)

    d.rounded_rectangle([x + 22, y + 80, x + w - 22, y + 124], radius=10,
                        fill=(255, 255, 255), outline=(218, 215, 208), width=2)
    d.text((x + 38, y + 102), "杭州", font=font(17), fill=INK, anchor="lm")
    d.line([x + 76, y + 90, x + 76, y + 114], fill=(60, 110, 200), width=2)

    d.text((x + 22, y + 136), "填写你所在的城市，留空默认北京", font=font(12, NOTO), fill=GREY)

    d.rounded_rectangle([x + 22, y + h - 58, x + w - 22, y + h - 18], radius=12,
                        fill=(38, 38, 40))
    d.text((x + w / 2, y + h - 38), "添加到设备", font=font(16, NOTO),
           fill=(250, 250, 248), anchor="mm")


def draw_device(bg, x, y, w, h):
    """③ Quote/0 屏幕实际显示"""
    # 机身
    paste_rounded(bg, Image.new("RGB", (w, h), (231, 227, 218)), (x, y), 26)

    # 屏幕：296:152 ≈ 1.947
    sw = w - 44
    sh = int(sw / 1.947)
    sx = x + 22
    sy = y + (h - sh) // 2

    bg.paste(Image.new("RGB", (sw, sh), (250, 249, 245)), (sx, sy))

    d = ImageDraw.Draw(bg)
    # 屏幕内凹边框
    d.rectangle([sx - 1, sy - 1, sx + sw, sy + sh], outline=(205, 201, 192), width=1)

    pad = 20
    k = sw / 296.0

    # 上行：温度 + 天气 + 体感（左），湿度 AQI（右）
    d.text((sx + pad, sy + 14), "6~22℃  晴  舒适",
           font=font(int(15 * k * 1.2), NOTO), fill=INK)
    d.text((sx + sw - pad, sy + 16), "湿度15%  AQI良",
           font=font(int(12 * k), NOTO), fill=(96, 94, 88), anchor="ra")
    d.line([sx + pad, sy + 42, sx + sw - pad, sy + 42], fill=(232, 229, 222), width=1)

    # 中行：诗句
    f_poem = font(int(21 * k))
    cy = sy + sh * 0.55
    d.text((sx + sw / 2, cy - int(19 * k)), "银烛秋光冷画屏，",
           font=f_poem, fill=INK, anchor="mm")
    d.text((sx + sw / 2, cy + int(19 * k)), "轻罗小扇扑流萤。",
           font=f_poem, fill=INK, anchor="mm")

    # 下行：出处 + 日期
    d.text((sx + sw - pad, sy + sh - 32), "——杜牧（唐）《秋夕》",
           font=font(int(12 * k), NOTO), fill=(70, 68, 64), anchor="ra")
    d.text((sx + pad, sy + sh - 30), "10月30日 周五",
           font=font(int(11 * k), NOTO), fill=(120, 118, 112))


def main():
    bg = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(bg)

    d.text((54, 40), "内容工坊上线后的样子（示意）", font=font(30), fill=INK)
    d.text((54, 86), "从卡片入口，到设备上真正读到的内容", font=font(15, NOTO), fill=GREY)

    draw_card(bg, 54, 150, 230, 240)
    draw_form(bg, 344, 150, 260, 240)
    draw_device(bg, 668, 140, 460, 250)

    # 箭头
    for x0, x1, y0 in ((300, 334, 270), (622, 656, 270)):
        d.line([x0, y0, x1 - 12, y0], fill=LIGHT, width=3)
        d.polygon([(x1 - 12, y0 - 7), (x1, y0), (x1 - 12, y0 + 7)], fill=LIGHT)

    labels = [("① 内容工坊里看到它", 54), ("② 填自己所在城市", 344), ("③ 设备上每天读一句", 668)]
    for text, x in labels:
        d.text((x, 416), text, font=font(15, NOTO), fill=(70, 68, 64))

    d.text((668, 452), "设备排版按接口返回的 display 字段示意；", font=font(12, NOTO), fill=GREY)
    d.text((668, 472), "最终样式由 Dot 侧模板决定，可能与此处不同。", font=font(12, NOTO), fill=GREY)

    bg.save(OUT)
    print("已生成", OUT)


if __name__ == "__main__":
    main()
