#!/usr/bin/env python3
"""诗词天气 - 根据每日天气推送古诗词到 Dot. 墨水屏

用法：
    python main.py

首次使用前，请复制 config.example.json 为 config.json 并填入你的密钥信息。
支持 IP 自动定位（当 config.json 中未指定经纬度时自动启用）。

edition 选项：
    general (默认) - 通用古诗词库，唐宋为主，137 首
    （未来可扩展 ci 纯宋词版，预留接口位，当前只有 general）

诗词库查找顺序：
    $POETRY_WEATHER_CONFIG 环境变量指向的路径（推荐放在 skill 之外的目录）
    → <scripts>/config.json（单用户向后兼容）
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from weather import fetch_weather, get_location_by_ip, WEATHER_EMOJI
from dot_api import push_to_device
from poetry import load_poetry, select_poem, CATEGORY_NAMES

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 配置文件查找顺序：环境变量 > skills/config.json，向后兼容旧用户
CONFIG_PATH = os.environ.get("POETRY_WEATHER_CONFIG") or os.path.join(SCRIPT_DIR, "config.json")
# 历史记录与 config 同目录（避免 skill 更新时丢失推送历史）
HISTORY_DIR = os.path.dirname(CONFIG_PATH)
HISTORY_PATH = os.path.join(HISTORY_DIR, "history.json")

# 去重窗口：窗口内推送过的诗词不会被再次选中（天）
DEDUP_DAYS = 20

# 支持的诗词版本（当前只 general；预留扩展位，未来加宋词版时改此处）
SUPPORTED_EDITIONS = ("general",)


def load_config():
    """读取配置文件

    查找顺序：
    1. $POETRY_WEATHER_CONFIG 环境变量指向的路径（推荐 skill 外）
    2. <scripts>/config.json（默认，向后兼容）
    """
    if not os.path.exists(CONFIG_PATH):
        if os.environ.get("POETRY_WEATHER_CONFIG"):
            print(f"❌ 环境变量 POETRY_WEATHER_CONFIG 指向的路径不存在：{CONFIG_PATH}")
        else:
            print("❌ 未找到 config.json，请先复制 config.example.json 为 config.json 并填写你的信息。")
            print("   提示：可通过环境变量 POETRY_WEATHER_CONFIG 指定配置文件路径（推荐放在 skill 之外）。")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_history():
    """读取推送历史，用于避免重复"""
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"sent": []}


def save_history(history):
    """保存推送历史"""
    history["sent"] = history["sent"][-200:]
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def build_last_sent(history, edition=None):
    """从推送历史构建 {title|author: 最近一次推送时间戳} 时间表

    Args:
        history: 推送历史 dict（含 "sent" 列表）
        edition: 仅取该版本的推送记录（None = 不过滤，等同 historical 行为）
    """
    last_sent = {}
    for item in history["sent"]:
        # 按 edition 隔离，避免通用版记录影响宋词版选诗
        if edition is not None and item.get("edition", "general") != edition:
            continue
        key = f'{item.get("title", "")}|{item.get("author", "")}'
        ts = item.get("timestamp", "")
        if not key:
            continue
        if key not in last_sent or ts > last_sent[key]:
            last_sent[key] = ts
    return last_sent


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

    # 4. 匹配诗词（排除 DEDUP_DAYS 天内推送过的诗）
    print(f"\n📚 匹配诗词（{DEDUP_DAYS}天内不重复）...")
    # 读取版本（config.json 中 edition 字段，缺省 general；非法值回退 general）
    edition = config.get("edition", "general").lower().strip()
    if edition not in SUPPORTED_EDITIONS:
        print(f"   ⚠️ edition={edition!r} 不支持，回退到 general。可选值：{', '.join(SUPPORTED_EDITIONS)}")
        edition = "general"
    poetry_db = load_poetry(edition=edition)

    history = load_history()
    # 去重按 edition 隔离：避免通用版推送记录影响宋词版选诗
    last_sent = build_last_sent(history, edition=edition)

    poem, matched_trigger = select_poem(poetry_db, weather["triggers"], last_sent, DEDUP_DAYS)

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
        "edition": edition,
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
