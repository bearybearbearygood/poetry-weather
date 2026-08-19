#!/usr/bin/env python3
"""诗词天气 - RSS Feed 服务

通过 RSS 订阅方式让 Dot. 墨水屏设备展示每日天气诗词。
用户只需在 Dot. App 的内容工坊中添加 RSS 订阅，填入 RSS 链接即可。

RSS 链接格式：
  /rss                    默认北京
  /rss?city=上海          按城市名
  /rss?lng=121.47&lat=31.23  按经纬度

特性：
  - 每日缓存：同一天同一城市返回相同内容（天气+诗词）
  - 标准 RSS 2.0 格式，Dot. 服务器自动定时拉取
  - 无需用户注册、无需提供 API 密钥
"""

import json
import os
import sys
import random
import hashlib
from datetime import datetime, date
from xml.sax.saxutils import escape

from flask import Flask, render_template, request, Response, jsonify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from weather import fetch_weather
from poetry import load_poetry, select_poem, get_season, CATEGORY_NAMES
from dot_api import generate_image, push_to_device

# ── 配置 ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
CITIES_PATH = os.path.join(SCRIPT_DIR, "cities.json")


def load_config():
    """加载配置（优先环境变量，其次 config.json）"""
    config = {
        "caiyun_token": "",
        "port": 8080,
        "default_lng": 116.4074,
        "default_lat": 39.9042,
        "default_city": "北京",
    }
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            fc = json.load(f)
        config["caiyun_token"] = fc.get("caiyun_token", "")
        loc = fc.get("location", {})
        if loc:
            config["default_lng"] = loc.get("lng", config["default_lng"])
            config["default_lat"] = loc.get("lat", config["default_lat"])
            config["default_city"] = loc.get("name", config["default_city"])

    config["caiyun_token"] = os.environ.get("CAIYUN_TOKEN", config["caiyun_token"])
    config["port"] = int(os.environ.get("PORT", config["port"]))
    return config


def load_cities():
    with open(CITIES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Flask 应用 ──
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "poetry-weather-rss")
CONFIG = load_config()

# ── 诗词文库（edition 可切换）──
# general: 通用古诗词混编；ci: 宋词版
EDITION_MAP = {
    "general": "poetry.json",
    "ci": "poetry_ci.json",
}
EDITION_LABELS = {
    "general": "诗词天气",
    "ci": "宋词版",
}
POETRY_DBS = {
    ed: load_poetry(os.path.join(SCRIPT_DIR, fn))
    for ed, fn in EDITION_MAP.items()
}
CITIES = load_cities()

# 默认版本（可被 --edition 启动参数覆盖，用于"独立运行某一版本"）
DEFAULT_EDITION = "general"


def resolve_edition(edition):
    """校验并解析 edition 参数，非法值回退到 general"""
    return edition if edition in POETRY_DBS else "general"

# ── 每日缓存 ──
# cache_key → {"date": "2026-08-04", "data": {...}}
# 同一天同一位置只请求一次天气 API + 选一次诗
_daily_cache = {}


def get_date_str():
    """返回当前日期字符串，如 '8月4日 周二'"""
    now = datetime.now()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return f"{now.month}月{now.day}日 {weekdays[now.weekday()]}"


def parse_location():
    """从请求参数解析位置，返回 (lng, lat, city_name)"""
    # 优先经纬度
    lng = request.args.get("lng")
    lat = request.args.get("lat")
    if lng and lat:
        try:
            return float(lng), float(lat), "自定义位置"
        except ValueError:
            pass

    # 城市名
    city = request.args.get("city", "").strip()
    if city and city in CITIES:
        lng, lat = CITIES[city]
        return lng, lat, city

    # 默认
    return CONFIG["default_lng"], CONFIG["default_lat"], CONFIG["default_city"]


def generate_daily_content(lng, lat, city_name, edition="general"):
    """获取天气 + 匹配诗词，返回内容字典"""
    db = POETRY_DBS.get(edition, POETRY_DBS["general"])
    weather = fetch_weather(CONFIG["caiyun_token"], lng, lat)

    # 使用日期+坐标+版本作为随机种子，保证同一天同一位置同一版本选到同一首
    today = date.today().isoformat()
    seed_str = f"{today}_{lng}_{lat}_{edition}"
    seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    poem, matched_trigger = select_poem(db, weather["triggers"], rng=rng)
    if not poem:
        poem = {"title": "无题", "author": "佚名", "lines": ["今日无诗"], "dynasty": ""}

    return {
        "date": today,
        "weather": weather,
        "poem": poem,
        "city": city_name,
        "edition": edition,
        "matched_trigger": matched_trigger,
    }


def get_cached_content(lng, lat, city_name, edition="general"):
    """获取缓存内容（同一天同一位置同一版本只生成一次）"""
    cache_key = f"{edition}:{lng:.4f},{lat:.4f}"
    today = date.today().isoformat()

    cached = _daily_cache.get(cache_key)
    if cached and cached["date"] == today:
        return cached["data"]

    # 生成新内容
    try:
        data = generate_daily_content(lng, lat, city_name, edition)
    except Exception as e:
        # 如果天气 API 失败，返回一个降级内容
        data = {
            "date": today,
            "weather": None,
            "poem": {
                "title": "无题",
                "author": "佚名",
                "lines": ["天气服务暂时不可用", str(e)[:50]],
                "dynasty": "",
            },
            "city": city_name,
            "edition": edition,
            "matched_trigger": None,
            "error": str(e),
        }

    _daily_cache[cache_key] = {"date": today, "data": data}
    return data


def build_rss_title(weather):
    """构建 RSS item 标题：温度区间 + 天气状况 + 舒适度"""
    if not weather:
        return "诗词天气"
    parts = []
    temp_min = weather.get("temp_min")
    temp_max = weather.get("temp_max")
    if temp_min is not None and temp_max is not None:
        parts.append(f"{temp_min}~{temp_max}℃")
    elif weather.get("temperature") is not None:
        parts.append(f'{weather["temperature"]}℃')
    if weather.get("description"):
        parts.append(weather["description"])
    if weather.get("comfort_desc"):
        parts.append(weather["comfort_desc"])
    return " ".join(parts) if parts else "诗词天气"


def build_rss_description(poem, weather, date_str, city):
    """构建 RSS item 描述：仅诗句 + 出处

    Dot. 渲染 RSS 时不识别 \\n 和 <br>，所有内容显示为一行。
    因此 description 只保留诗句和出处，天气详情不放入。
    """
    parts = []

    # 诗句
    poem_lines = poem.get("lines", [])
    parts.extend(poem_lines)

    # 出处
    author = poem.get("author", "")
    poem_title = poem.get("title", "无题")
    dynasty = poem.get("dynasty", "")
    if dynasty:
        source = f"——{author}（{dynasty}）《{poem_title}》"
    else:
        source = f"——{author}《{poem_title}》"
    parts.append(source)

    return " ".join(parts)


def generate_rss_xml(content):
    """生成 RSS 2.0 XML"""
    weather = content.get("weather")
    poem = content.get("poem", {})
    city = content.get("city", "")
    edition = content.get("edition", "general")
    date_str = get_date_str()

    title = build_rss_title(weather)
    description = build_rss_description(poem, weather, date_str, city)

    today = date.today().isoformat()
    guid = f"poetry-weather-{edition}-{today}-{city}"

    # pubDate: 只保留日期，去掉时间（Dot. 底部会显示 pubDate，00:00 无意义）
    pub_date = datetime.now().strftime("%a, %d %b %Y +0800")

    # 基础 URL（从请求头推断）
    base_url = request.host_url.rstrip("/")
    channel_title = f'{EDITION_LABELS.get(edition, "诗词天气")} - {city}'

    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        '  <channel>',
        f'    <title>{escape(channel_title)}</title>',
        f'    <link>{escape(base_url)}</link>',
        '    <description>根据每日天气，自动匹配古诗词</description>',
        '    <language>zh-CN</language>',
        '    <ttl>60</ttl>',
        '    <item>',
        f'      <title>{escape(title)}</title>',
        f'      <description>{escape(description)}</description>',
        f'      <guid isPermaLink="false">{escape(guid)}</guid>',
        f'      <pubDate>{pub_date}</pubDate>',
        '    </item>',
        '  </channel>',
        '</rss>',
    ]

    return "\n".join(xml_parts)


# ── 路由 ──

@app.route("/")
def index():
    """首页：RSS 订阅说明"""
    editions = [{"id": k, "name": v} for k, v in EDITION_LABELS.items()]
    return render_template("index.html", cities=CITIES, editions=editions)


@app.route("/rss")
def rss():
    """RSS Feed 端点，支持 ?edition=ci 切换版本；默认版本由 DEFAULT_EDITION 决定"""
    lng, lat, city_name = parse_location()
    edition = resolve_edition(request.args.get("edition", DEFAULT_EDITION))
    content = get_cached_content(lng, lat, city_name, edition)
    xml = generate_rss_xml(content)
    return Response(xml, mimetype="application/rss+xml; charset=utf-8")


@app.route("/preview")
def preview():
    """预览今日内容（JSON），支持 ?edition=ci 切换版本"""
    lng, lat, city_name = parse_location()
    edition = resolve_edition(request.args.get("edition", DEFAULT_EDITION))
    content = get_cached_content(lng, lat, city_name, edition)

    weather = content.get("weather")
    poem = content.get("poem", {})
    date_str = get_date_str()

    return jsonify({
        "city": city_name,
        "date": date_str,
        "title": build_rss_title(weather),
        "description": build_rss_description(poem, weather, date_str, city_name),
        "poem": {
            "title": poem.get("title", ""),
            "author": poem.get("author", ""),
            "dynasty": poem.get("dynasty", ""),
            "lines": poem.get("lines", []),
        },
        "weather": {
            "temperature": weather.get("temperature") if weather else None,
            "temp_min": weather.get("temp_min") if weather else None,
            "temp_max": weather.get("temp_max") if weather else None,
            "description": weather.get("description") if weather else None,
            "humidity": weather.get("humidity") if weather else None,
            "wind_speed": weather.get("wind_speed") if weather else None,
            "aqi_desc": weather.get("aqi_desc") if weather else None,
            "comfort_desc": weather.get("comfort_desc") if weather else None,
        } if weather else None,
        "matched_trigger": content.get("matched_trigger"),
    })


@app.route("/api/cities")
def api_cities():
    """城市列表 API"""
    return jsonify(CITIES)


@app.route("/screen")
def screen():
    """墨水屏效果预览（本地验证"能不能成功显示"用），支持 ?edition=ci"""
    lng, lat, city_name = parse_location()
    edition = resolve_edition(request.args.get("edition", DEFAULT_EDITION))
    content = get_cached_content(lng, lat, city_name, edition)
    weather = content.get("weather")
    poem = content.get("poem", {})
    date_str = get_date_str()

    title = build_rss_title(weather)
    description = build_rss_description(poem, weather, date_str, city_name)

    # 预览页面用自己的 HTML 排版（与 Dot. 实际渲染无关）
    poem_html = "<br>".join(escape(ln) for ln in poem.get("lines", []))
    author = poem.get("author", "")
    poem_title = poem.get("title", "无题")
    dynasty = poem.get("dynasty", "")
    source = f"——{author}（{dynasty}）《{poem_title}》" if dynasty else f"——{author}《{poem_title}》"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>墨水屏效果预览 - {escape(city_name)}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#e9e9e9; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; display:flex; justify-content:center; padding:32px; }}
  /* 模拟 Dot. quote 墨水屏：暖白底、黑字、无彩色 */
  .screen {{ width:360px; min-height:480px; background:#f7f5ef; color:#1a1a1a;
            border:1px solid #cfcabb; border-radius:10px; padding:36px 28px;
            display:flex; flex-direction:column; justify-content:space-between;
            box-shadow:0 6px 24px rgba(0,0,0,.12); }}
  .top {{ font-size:15px; letter-spacing:.5px; color:#333; }}
  .body {{ font-size:20px; line-height:2.0; text-align:center; }}
  .body .source {{ font-size:15px; color:#444; margin-top:10px; }}
  .tag {{ display:inline-block; font-size:11px; color:#777; border:1px solid #ccc; border-radius:4px; padding:1px 6px; margin-bottom:10px; }}
</style>
</head>
<body>
  <div class="screen">
    <div class="top"><span class="tag">{escape(EDITION_LABELS.get(edition, "诗词天气"))}</span><br>{escape(title)}</div>
    <div class="body">{poem_html}<div class="source">{escape(source)}</div></div>
  </div>
</body>
</html>"""


@app.route("/image")
def image():
    """生成并返回 296×152 墨水屏 PNG 图片（与 Image API 推送的一致）"""
    lng, lat, city_name = parse_location()
    edition = resolve_edition(request.args.get("edition", DEFAULT_EDITION))
    content = get_cached_content(lng, lat, city_name, edition)
    weather = content.get("weather")
    poem = content.get("poem", {})
    date_str = get_date_str()

    png_data = generate_image(poem, weather, date_str)
    return Response(png_data, mimetype="image/png")


@app.route("/push")
def push():
    """远程生成图片并推送到 Dot. 设备（供外部定时器调用，实现每日自动推送）

    需要 environment 变量 DOT_API_KEY 和 DOT_DEVICE_ID，
    或在 URL 中传 ?api_key=xxx&device_id=xxx
    """
    api_key = os.environ.get("DOT_API_KEY", "")
    device_id = os.environ.get("DOT_DEVICE_ID", "")

    # URL 参数可覆盖环境变量（测试用）
    api_key = request.args.get("api_key", api_key)
    device_id = request.args.get("device_id", device_id)

    if not api_key or not device_id:
        return jsonify({
            "success": False,
            "error": "未配置 DOT_API_KEY 或 DOT_DEVICE_ID。请在 Render 环境变量中设置，或通过 URL 参数传入。"
        }), 400

    lng, lat, city_name = parse_location()
    edition = resolve_edition(request.args.get("edition", DEFAULT_EDITION))
    content = get_cached_content(lng, lat, city_name, edition)
    weather = content.get("weather")
    poem = content.get("poem", {})
    date_str = get_date_str()

    try:
        msg = push_to_device(api_key, device_id, poem, weather, date_str)
        return jsonify({
            "success": True,
            "message": msg,
            "city": city_name,
            "poem": f'{poem.get("author", "")}《{poem.get("title", "")}》',
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── 启动 ──

def main():
    import argparse
    parser = argparse.ArgumentParser(description="诗词天气 RSS 服务")
    parser.add_argument("--edition", default=None,
                        help="默认诗词版本：general（通用）/ ci（宋词版）。设置后 RSS 默认走该版本，无需在 URL 带参数。")
    parser.add_argument("--port", type=int, default=None, help="监听端口（覆盖配置）")
    args = parser.parse_args()

    global DEFAULT_EDITION
    if args.edition:
        DEFAULT_EDITION = resolve_edition(args.edition)

    if not CONFIG["caiyun_token"]:
        print("警告: 未配置 caiyun_token，请在 config.json 或环境变量 CAIYUN_TOKEN 中设置")

    port = args.port or CONFIG["port"]
    print(f"诗词天气 RSS 服务已启动: http://0.0.0.0:{port}")
    print(f"  当前默认版本: {EDITION_LABELS.get(DEFAULT_EDITION, DEFAULT_EDITION)}")
    print(f"  通用版 RSS: http://0.0.0.0:{port}/rss")
    print(f"  宋词版 RSS: http://0.0.0.0:{port}/rss?edition=ci")
    print(f"  墨水屏预览: http://0.0.0.0:{port}/screen?edition=ci")
    print(f"  预览地址: http://0.0.0.0:{port}/preview")
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
