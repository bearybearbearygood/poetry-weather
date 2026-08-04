#!/usr/bin/env python3
"""诗词天气 - 根据每日天气推送古诗词到 Dot. 墨水屏

用法：
    python main.py

首次使用前，请复制 config.example.json 为 config.json 并填入你的密钥信息。
支持 IP 自动定位（当 config.json 中未指定经纬度时自动启用）。
"""

import json
import os
import sys
import random
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from weather import fetch_weather, get_location_by_ip, WEATHER_EMOJI
from dot_api import push_to_device

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
POETRY_PATH = os.path.join(SCRIPT_DIR, "poetry.json")
HISTORY_PATH = os.path.join(SCRIPT_DIR, "history.json")

# 天气类型的中文名称
CATEGORY_NAMES = {
    "clear": "晴", "partly_cloudy": "多云", "cloudy": "阴",
    "rain": "雨", "heavy_rain": "大雨", "snow": "雪", "heavy_snow": "大雪",
    "fog": "雾", "haze": "霾", "wind": "大风", "dust": "沙尘",
    "hot": "高温", "cold": "严寒",
}


def get_season():
    """根据当前月份判断季节"""
    month = datetime.now().month
    if month in (3, 4, 5):
        return "spring"
    elif month in (6, 7, 8):
        return "summer"
    elif month in (9, 10, 11):
        return "autumn"
    else:
        return "winter"


def load_config():
    """读取配置文件"""
    if not os.path.exists(CONFIG_PATH):
        print("❌ 未找到 config.json，请先复制 config.example.json 为 config.json 并填写你的信息。")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_poetry():
    """读取诗词数据库"""
    with open(POETRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_history():
    """读取推送历史，用于避免重复"""
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"sent": []}


def save_history(history):
    """保存推送历史"""
    history["sent"] = history["sent"][-50:]
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def resolve_location(config):
    """解析地理位置

    优先使用 config.json 中的经纬度，否则通过 IP 自动定位。
    """
    location = config.get("location", {})
    lng = location.get("lng")
    lat = location.get("lat")

    if lng is not None and lat is not None:
        name = location.get("name", "已配置")
        return lng, lat, name

    # IP 自动定位
    print("   未配置经纬度，正在通过 IP 自动定位...")
    result = get_location_by_ip()
    if result:
        lng, lat, city = result
        print(f"   定位成功: {city} ({lng}, {lat})")
        return lng, lat, city

    print("   ⚠️ IP 定位失败，使用默认位置（北京）")
    return 116.4074, 39.9042, "北京（默认）"


def select_poem(poetry_db, triggers, history):
    """从诗词库中选择一首诗

    多维度匹配：
      1. 优先匹配所有触发条件中更"特殊"的（hot/cold > 天气类型）
      2. 同一类别内优先选当季的诗
      3. 排除最近推送过的诗

    Args:
        poetry_db: 诗词数据库
        triggers: 触发条件列表，如 ["clear", "hot"]
        history: 推送历史
    """
    current_season = get_season()

    # 按优先级排序触发条件：hot/cold 优先，其次按顺序
    priority = {"hot": 0, "cold": 0, "heavy_rain": 1, "heavy_snow": 1,
                "dust": 2, "haze": 2, "fog": 2, "wind": 2,
                "rain": 3, "snow": 3, "cloudy": 4,
                "partly_cloudy": 5, "clear": 6}
    sorted_triggers = sorted(triggers, key=lambda t: priority.get(t, 99))

    # 收集最近推送过的诗
    recent = set()
    for item in history["sent"][-20:]:
        recent.add(f'{item.get("title", "")}|{item.get("author", "")}')

    # 按触发优先级依次尝试
    for trigger in sorted_triggers:
        poems = poetry_db.get(trigger, [])
        if not poems:
            continue

        # 优先选当季
        seasonal = [p for p in poems if p.get("season") == current_season or p.get("season") == "all"]
        pool = seasonal if seasonal else poems

        # 排除最近推送过的
        available = [p for p in pool if f'{p.get("title", "")}|{p.get("author", "")}' not in recent]
        if not available:
            available = pool

        return random.choice(available), trigger

    # 兜底
    fallback = poetry_db.get("clear", poetry_db.get("rain", []))
    if fallback:
        return random.choice(fallback), "fallback"

    return None, None


def main():
    print("=" * 56)
    print("  诗词天气 - 天气驱动的每日诗词推送")
    print("=" * 56)

    # 1. 读取配置
    config = load_config()
    caiyun_token = config.get("caiyun_token", "")
    dot_api_key = config.get("dot_api_key", "")
    device_id = config.get("device_id", "")

    if not caiyun_token:
        print("❌ 请在 config.json 中填写 caiyun_token")
        sys.exit(1)
    if not dot_api_key or not device_id:
        print("❌ 请在 config.json 中填写 dot_api_key 和 device_id")
        sys.exit(1)

    # 2. 解析位置
    print("\n📍 定位中...")
    lng, lat, loc_name = resolve_location(config)
    print(f"   位置: {loc_name} ({lng}, {lat})")

    # 3. 获取天气
    print(f"\n📡 获取天气数据...")
    try:
        weather = fetch_weather(caiyun_token, lng, lat)
    except RuntimeError as e:
        print(f"❌ 获取天气失败: {e}")
        sys.exit(1)

    # 打印天气详情
    temp = weather.get("temperature")
    temp_str = f'{temp}°C' if temp is not None else "N/A"
    feels = weather.get("apparent_temp")
    feels_str = f'（体感{feels}°C）' if feels is not None else ""
    humidity = weather.get("humidity")
    humidity_str = f'{humidity}%' if humidity is not None else "N/A"
    wind = weather.get("wind_speed")
    wind_str = f'{round(wind)}m/s' if wind is not None else "N/A"
    t_max = weather.get("temp_max")
    t_min = weather.get("temp_min")
    range_str = f'{t_min}~{t_max}°C' if t_max is not None and t_min is not None else ""

    print(f"   天气: {weather['emoji']} {weather['description']} · {temp_str}{feels_str}")
    print(f"   温度: {range_str}  湿度: {humidity_str}  风速: {wind_str}")
    if weather.get("aqi_desc"):
        print(f"   空气: {weather['aqi_desc']}(AQI {weather.get('aqi', '?')})  舒适: {weather.get('comfort_desc', 'N/A')}")
    print(f"   触发: {', '.join(weather['triggers'])}")

    # 4. 匹配诗词
    print(f"\n📚 匹配诗词...")
    poetry_db = load_poetry()
    history = load_history()

    poem, matched_trigger = select_poem(poetry_db, weather["triggers"], history)

    if not poem:
        print("❌ 未找到合适的诗词")
        sys.exit(1)

    trigger_name = CATEGORY_NAMES.get(matched_trigger, matched_trigger)
    print(f"   匹配类型: {trigger_name}")
    print(f"   选中: 《{poem['title']}》 {poem['dynasty']}·{poem['author']}")
    for line in poem["lines"]:
        print(f"         {line.strip()}")

    # 5. 推送到设备
    now = datetime.now()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    date_str = f'{now.month}月{now.day}日 {weekdays[now.weekday()]}'

    print(f"\n📺 推送到设备 {device_id}...")
    try:
        result = push_to_device(dot_api_key, device_id, poem, weather, date_str)
        print(f"   ✅ {result}")
    except RuntimeError as e:
        print(f"❌ 推送失败: {e}")
        sys.exit(1)

    # 6. 记录历史
    history["sent"].append({
        "title": poem.get("title", ""),
        "author": poem.get("author", ""),
        "dynasty": poem.get("dynasty", ""),
        "weather": weather["description"],
        "temperature": temp,
        "triggers": weather["triggers"],
        "date": date_str,
        "timestamp": now.isoformat(),
    })
    save_history(history)

    print(f"\n✨ 完成！诗词已推送到你的 Dot. 设备。")
    print("=" * 56)


if __name__ == "__main__":
    main()
