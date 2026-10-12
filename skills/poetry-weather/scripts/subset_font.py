#!/usr/bin/env python3
"""生成诗词天气专用子集字体

从诗词库（poetry.json / poetry_ci.json）+ UI 常用字符串中抽取全部字符，
用 fonttools 对 Noto Sans CJK SC 做子集化，生成 ~百 KB 级小字体，
随安装包分发，用户无需自装中文字体。

用法:
    python3 subset_font.py [输入字体] [输出路径]

依赖: fonttools (pip install fonttools)
"""
import json
import os
import re
import sys
from fontTools import subset

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

POETRY_FILES = [
    os.path.join(PROJECT_DIR, "poetry.json"),
    os.path.join(PROJECT_DIR, "poetry_ci.json"),
]
INPUT_FONT = os.path.join(PROJECT_DIR, "fonts", "NotoSansCJKsc-Regular.otf")
OUTPUT_FONT = os.path.join(PROJECT_DIR, "fonts", "poetry-weather.ttf")

# ── UI 固定字符（天气/日期/农历/节气/空气质量等，与代码里出现的字符串对齐）──
UI_CHARS = (
    # 天气描述
    "晴多云阴雨雪雾霾风沙尘雹夹冰"
    "小中大暴轻度中度重度浮扬沙"
    # 温度/湿度/AQI
    "℃湿度空气优良污染严"
    # 半角百分号（PIL 渲染湿度时作为独立字符，需显式列入；半角字符覆盖不全易缺）
    "%"
    "~·"
    # 舒适度
    "炎热闷酷温凉寒冷严寒"
    # 农历
    "农历一二三四五六七八九十廿卅正腊冬闰月初"
    # 日期
    "年月日周"
    # 节气（二十四节气）
    "立春雨水惊蛰春分清明谷雨夏小满芒种至暑大处白露秋寒霜降冬雪小大雪冬至"
    # 标题/出处标点
    "——《》、，。！？；：""''「」【】·…"
    # 数字
    "0123456789"
    # 其它
    "诗无题版"
)


def collect_chars():
    chars = set(UI_CHARS)
    for path in POETRY_FILES:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            db = json.load(f)
        def walk(obj):
            if isinstance(obj, str):
                chars.update(obj)
            elif isinstance(obj, dict):
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)
        walk(db)
    # 去掉空白/控制字符，保留可打印字符
    return "".join(sorted(ch for ch in chars if ch.strip()))


def main():
    args = sys.argv[1:]
    input_font = args[0] if len(args) > 0 else INPUT_FONT
    output_font = args[1] if len(args) > 1 else OUTPUT_FONT

    text = collect_chars()
    print(f"共抽取 {len(text)} 个字符")
    print(f"输入: {input_font}")
    print(f"输出: {output_font}")

    options = subset.Options()
    options.flavor = None          # 输出 ttf/otf（非 woff2）
    options.desubroutinize = True  # CFF 子集化后重新生成
    options.layout_features = ["*"]
    options.name_IDs = [1, 2, 4, 6, 16, 17]
    options.name_legacy = False
    options.name_languages = ["*"]

    s = subset.Subsetter(options=options)
    s.populate(text=text)
    font = subset.load_font(input_font, options)
    s.subset(font)
    subset.save_font(font, output_font, options)
    size = os.path.getsize(output_font)
    print(f"完成，子集字体大小: {size/1024:.0f} KB")


if __name__ == "__main__":
    main()
