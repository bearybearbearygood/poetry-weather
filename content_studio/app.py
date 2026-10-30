#!/usr/bin/env python3
"""诗词天气 · Dot 内容工坊接口服务

只做一件事：给 Dot 内容工坊提供一个只读接口。

    GET /api/daily?city=杭州

设计约束：
  - 完全独立于主项目的 rss_server.py / main.py / server.py，不 import、不修改
  - 诗库与主项目共用同一份 poetry.json（只读），避免两处维护导致内容不一致
  - 无状态：不写数据库、不采集用户身份或位置信息
  - 城市完全由用户填写，服务端不做任何 IP 定位

运行：
  CAIYUN_TOKEN=xxx python3 app.py
"""

import hashlib
import json
import os
import random
import sys
import threading
from datetime import date, datetime

from flask import Flask, jsonify, request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# 诗库与选诗逻辑复用主项目（只读，不改动）
# 注意用 append 而不是 insert(0)：本目录的 weather.py / geocode.py 必须优先于
# 根目录同名模块，否则会把主项目那份 import 进来
sys.path.append(PROJECT_ROOT)

from poetry import load_poetry, select_poem  # noqa: E402

# 本目录内的独立实现
from geocode import resolve_city  # noqa: E402
from weather import fetch_weather_any  # noqa: E402

POETRY_PATH = os.path.join(PROJECT_ROOT, "poetry.json")

DEFAULT_CITY = "北京"
DEFAULT_LNG = 116.4074
DEFAULT_LAT = 39.9042

# 缓存策略：同一天、同一坐标只生成一次
# Dot 侧会定时拉取，没必要每次都打天气 API
CACHE_TTL_HINT = 1800  # 对外声明的建议缓存秒数

app = Flask(__name__)

_config = None
_poetry_db = None
_cache = {}
_cache_lock = threading.Lock()


def load_config():
    """配置只从环境变量读，避免和主项目的 config.json 互相干扰"""
    return {
        "caiyun_token": os.environ.get("CAIYUN_TOKEN", ""),
        "weather_provider": os.environ.get("WEATHER_PROVIDER", "qweather"),
        "default_city": os.environ.get("DEFAULT_CITY", DEFAULT_CITY),
    }


def get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_poetry_db():
    global _poetry_db
    if _poetry_db is None:
        _poetry_db = load_poetry(POETRY_PATH)
    return _poetry_db


def build_title(weather):
    """顶部一行：温度区间 + 天气 + 体感"""
    if not weather:
        return "诗词天气"
    parts = []
    if weather.get("temp_min") is not None and weather.get("temp_max") is not None:
        parts.append(f'{weather["temp_min"]}~{weather["temp_max"]}℃')
    elif weather.get("temperature") is not None:
        parts.append(f'{weather["temperature"]}℃')
    if weather.get("description"):
        parts.append(weather["description"])
    if weather.get("comfort_desc"):
        parts.append(weather["comfort_desc"])
    return " ".join(parts) if parts else "诗词天气"


def build_generated(lng, lat, city_name):
    """生成某地当日内容，带进程内日缓存"""
    today = date.today().isoformat()
    key = f"{lng:.4f},{lat:.4f}"

    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit["date"] == today:
            return hit["data"]

    cfg = get_config()
    weather = fetch_weather_any(
        cfg["weather_provider"], cfg["caiyun_token"], lng, lat
    )

    # 种子固定为 日期 + 坐标，保证同一天同一地点选到同一首
    seed_str = f"{today}_{lng}_{lat}"
    seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    poem, _trigger = select_poem(get_poetry_db(), weather["triggers"], rng=rng)
    if not poem:
        poem = {"title": "无题", "author": "佚名", "dynasty": "", "lines": ["今日无诗"]}

    data = {"weather": weather, "poem": poem, "date": today, "city": city_name}

    with _cache_lock:
        _cache[key] = {"date": today, "data": data}

    return data


def format_source(poem):
    author = poem.get("author", "")
    dynasty = poem.get("dynasty", "")
    title = poem.get("title", "无题")
    if dynasty:
        return f"——{author}（{dynasty}）《{title}》"
    return f"——{author}《{title}》"


@app.route("/api/daily")
def api_daily():
    raw_city = request.args.get("city", "").strip()
    cfg = get_config()

    if raw_city:
        hit = resolve_city(raw_city)
        if not hit:
            return jsonify({
                "ok": False,
                "error": "city_not_found",
                "message": f"无法解析这个城市：{raw_city}",
            }), 400
        lng, lat, city_name = hit["lng"], hit["lat"], hit["name"]
    else:
        lng, lat, city_name = DEFAULT_LNG, DEFAULT_LAT, cfg["default_city"]

    try:
        data = build_generated(lng, lat, city_name)
    except Exception as e:
        # 天气源故障时不让调用方拿到 200 的空内容
        return jsonify({
            "ok": False,
            "error": "weather_unavailable",
            "message": "天气数据暂时不可用，请稍后重试",
        }), 503

    weather = data["weather"]
    poem = data["poem"]
    now = datetime.now()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    payload = {
        "ok": True,
        "city": city_name,
        "date": data["date"],
        "date_text": f"{now.month}月{now.day}日 {weekdays[now.weekday()]}",
        "weather": {
            "text": weather.get("description"),
            "temperature": weather.get("temperature"),
            "temp_min": weather.get("temp_min"),
            "temp_max": weather.get("temp_max"),
            "humidity": weather.get("humidity"),
            "wind_speed": weather.get("wind_speed"),
            "comfort": weather.get("comfort_desc"),
            "aqi": weather.get("aqi"),
            "aqi_desc": weather.get("aqi_desc"),
        },
        "poem": {
            "title": poem.get("title", ""),
            "author": poem.get("author", ""),
            "dynasty": poem.get("dynasty", ""),
            "lines": poem.get("lines", []),
        },
        # 直接可渲染的三段文本，调用方不必理解上面的结构
        "display": {
            "title": build_title(weather),
            "lines": poem.get("lines", []),
            "source": format_source(poem),
        },
        "cache_ttl": CACHE_TTL_HINT,
    }

    resp = jsonify(payload)
    resp.headers["Cache-Control"] = f"public, max-age={CACHE_TTL_HINT}"
    return resp


@app.route("/health")
def health():
    cfg = get_config()
    return jsonify({
        "ok": True,
        "provider": cfg["weather_provider"],
        "city_table": _city_count(),
        "uptime_note": "stateless",
    })


_city_count_cache = None


def _city_count():
    global _city_count_cache
    if _city_count_cache is None:
        with open(os.path.join(SCRIPT_DIR, "cities_cn.json"), "r", encoding="utf-8") as f:
            _city_count_cache = len(json.load(f))
    return _city_count_cache


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8100))
    cfg = get_config()
    if cfg["weather_provider"] == "caiyun" and not cfg["caiyun_token"]:
        print("警告：未设置 CAIYUN_TOKEN，彩云通道不可用")
    if cfg["weather_provider"] == "qweather" and not os.environ.get("QWEATHER_HOST"):
        print("警告：未设置 QWEATHER_HOST，和风通道不可用")
    print(f"诗词天气 · 内容工坊接口 :{port}")
    print(f"  数据源：{cfg['weather_provider']}")
    print(f"  示例：http://127.0.0.1:{port}/api/daily?city=杭州")
    app.run(host="0.0.0.0", port=port)
