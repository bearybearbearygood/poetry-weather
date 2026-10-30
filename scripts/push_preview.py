#!/usr/bin/env python3
"""推送一张真实效果图到设备（验证排版用）

和每日推送走同一条链路，区别只在于天气数据用和风（与内容工坊同源）。
推送只更新循环列表里的 IMAGE_API 槽位，其他内容不受影响。

用法：python3 scripts/push_preview.py [城市]
"""

import importlib.util
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from dot_api import generate_image, get_image_api_task_key, push_to_device  # noqa: E402
from poetry import load_poetry, select_poem  # noqa: E402

sys.path.append(os.path.join(ROOT, "content_studio"))
from geocode import resolve_city  # noqa: E402

# 和风客户端在 content_studio 下，模块名与根目录的 weather 冲突，这里显式按路径加载
spec = importlib.util.spec_from_file_location(
    "weather_qweather", os.path.join(ROOT, "content_studio", "weather_qweather.py"))
wq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wq)


def main():
    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    city = sys.argv[1] if len(sys.argv) > 1 else cfg.get("location", {}).get("name", "北京")

    hit = resolve_city(city)
    if not hit:
        print(f"无法解析城市：{city}")
        return
    lng, lat = hit["lng"], hit["lat"]

    weather = wq.fetch_weather(lng, lat)
    db = load_poetry(os.path.join(ROOT, "poetry.json"))
    poem, trigger = select_poem(db, weather["triggers"])
    if not poem:
        poem = {"title": "无题", "author": "佚名", "dynasty": "", "lines": ["今日无诗"]}

    now = datetime.now()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    date_str = f"{now.month}月{now.day}日 {weekdays[now.weekday()]}"

    print(f"城市：{hit['name']}")
    print(f"天气：{weather['temp_min']}~{weather['temp_max']}℃ {weather['description']} "
          f"湿度{weather['humidity']}% AQI {weather['aqi_desc']} 舒适度 {weather['comfort_desc']}")
    print(f"触发：{weather['triggers']} → {trigger}")
    print(f"诗句：{' / '.join(poem['lines'])} —— {poem['author']}《{poem['title']}》")

    png = generate_image(poem, weather, date_str)
    out = os.path.join(ROOT, "content_studio", "assets", "device_preview.png")
    with open(out, "wb") as f:
        f.write(png)
    print(f"本地预览：{out}")

    key = get_image_api_task_key(cfg["dot_api_key"], cfg["device_id"])
    if not key:
        print("未找到 IMAGE_API 槽位，未推送")
        return
    print(f"目标槽位：{key}")

    msg = push_to_device(cfg["dot_api_key"], cfg["device_id"], poem, weather, date_str)
    print("推送结果：", msg)


if __name__ == "__main__":
    main()
