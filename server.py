#!/usr/bin/env python3
"""诗词天气 - 托管服务

一个 Web 服务，让多个用户注册后自动每天接收诗词天气推送。

功能：
  - 首页：说明文档（效果展示 + 设置步骤）
  - 注册：用户填写 Dot. API 密钥、设备序列号、城市
  - 管理：查看/更新/取消订阅，手动触发推送
  - 定时推送：每天早上自动为所有注册用户推送诗词天气

部署方式：
  方式一（Docker，推荐）：docker-compose up -d
  方式二（直接运行）：python server.py

配置（环境变量或 config.json）：
  CAIYUN_TOKEN: 彩云天气 API Token（服务共享）
  PUSH_HOUR: 每日推送小时（默认 7）
  PUSH_MINUTE: 每日推送分钟（默认 0）
  PORT: Web 服务端口（默认 5000）
"""

import json
import os
import sys
import random
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from weather import fetch_weather
from dot_api import build_text_payload, get_text_api_task_key, DOT_API_BASE
from poetry import load_poetry, select_poem, get_season, CATEGORY_NAMES
import db

import urllib.request
import urllib.error

# ── 配置 ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
CITIES_PATH = os.path.join(SCRIPT_DIR, "cities.json")

def load_service_config():
    """加载服务配置（优先环境变量，其次 config.json）"""
    # 默认值
    config = {
        "caiyun_token": "",
        "push_hour": 7,
        "push_minute": 0,
        "port": 8080,
    }

    # 从 config.json 读取
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            file_config = json.load(f)
        config["caiyun_token"] = file_config.get("caiyun_token", "")

    # 环境变量覆盖
    config["caiyun_token"] = os.environ.get("CAIYUN_TOKEN", config["caiyun_token"])
    config["push_hour"] = int(os.environ.get("PUSH_HOUR", config["push_hour"]))
    config["push_minute"] = int(os.environ.get("PUSH_MINUTE", config["push_minute"]))
    config["port"] = int(os.environ.get("PORT", config["port"]))

    return config


def load_cities():
    """加载城市列表"""
    with open(CITIES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Flask 应用 ──
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "poetry-weather-secret-key-change-me")

# 全局配置
SERVICE_CONFIG = load_service_config()
POETRY_DB = load_poetry()
CITIES = load_cities()

# ── 推送核心逻辑 ──

def get_date_str():
    """返回当前日期字符串，如 '8月4日 周二'"""
    now = datetime.now()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return f"{now.month}月{now.day}日 {weekdays[now.weekday()]}"


def push_to_subscriber(sub):
    """为单个订阅者推送诗词天气

    Args:
        sub: 订阅信息字典（含 dot_api_key, device_id, city, lng, lat）

    Returns:
        dict: 推送结果 {success, message, poem_title, poem_author, weather_desc, temperature}
    """
    result = {
        "success": False,
        "message": "",
        "poem_title": "",
        "poem_author": "",
        "weather_desc": "",
        "temperature": None,
    }

    # 1. 获取天气
    try:
        weather = fetch_weather(SERVICE_CONFIG["caiyun_token"], sub["lng"], sub["lat"])
    except Exception as e:
        result["message"] = f"天气获取失败: {e}"
        return result

    result["weather_desc"] = weather.get("description", "")
    result["temperature"] = weather.get("temperature")

    # 2. 获取该用户最近的推送历史（用于去重）
    recent_titles = set()
    history = db.get_push_history(sub["manage_token"], limit=20)
    for h in history:
        if h.get("poem_title") and h.get("poem_author"):
            recent_titles.add(f'{h["poem_title"]}|{h["poem_author"]}')

    # 3. 匹配诗词
    poem, matched_trigger = select_poem(POETRY_DB, weather["triggers"], recent_titles)
    if not poem:
        result["message"] = "未找到合适的诗词"
        return result

    result["poem_title"] = poem.get("title", "")
    result["poem_author"] = poem.get("author", "")

    # 4. 构建并推送
    date_str = get_date_str()
    payload = build_text_payload(poem, weather, date_str)

    # 设置任务别名，方便用户在 Dot. App 中识别
    payload["taskAlias"] = "诗词天气"

    # 查询并携带 taskKey
    task_key = get_text_api_task_key(sub["dot_api_key"], sub["device_id"])
    if task_key:
        payload["taskKey"] = task_key

    url = f"{DOT_API_BASE}/api/authV2/open/device/{sub['device_id']}/text"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {sub['dot_api_key']}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            result["success"] = True
            result["message"] = resp_data.get("message", "推送成功")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        try:
            error_msg = json.loads(error_body).get("message", error_body)
        except (json.JSONDecodeError, ValueError):
            error_msg = error_body or e.reason
        result["message"] = f"Dot. API 错误 {e.code}: {error_msg}"
    except urllib.error.URLError as e:
        result["message"] = f"无法连接 Dot. API: {e.reason}"
    except Exception as e:
        result["message"] = f"推送异常: {e}"

    return result


def push_all_subscribers():
    """为所有活跃订阅者推送诗词天气（由定时任务调用）"""
    subs = db.get_active_subscriptions()
    print(f"[{datetime.now().isoformat()}] 开始推送，共 {len(subs)} 个订阅")

    for sub in subs:
        print(f"  -> {sub['device_id']} ({sub['city']})...")
        result = push_to_subscriber(sub)

        status = "success" if result["success"] else "failed"
        error_msg = None if result["success"] else result["message"]

        db.record_push(
            subscription_id=sub["id"],
            device_id=sub["device_id"],
            poem_title=result["poem_title"],
            poem_author=result["poem_author"],
            weather_desc=result["weather_desc"],
            temperature=result["temperature"],
            status=status,
            error_msg=error_msg,
        )

        if result["success"]:
            print(f"     OK: {result['poem_title']} - {result['message']}")
        else:
            print(f"     FAIL: {result['message']}")

    print(f"[{datetime.now().isoformat()}] 推送完成")


# ── 路由 ──

@app.route("/")
def index():
    """首页：说明文档"""
    stats = db.get_stats()
    return render_template("index.html", stats=stats)


@app.route("/register", methods=["GET", "POST"])
def register():
    """注册页"""
    if request.method == "GET":
        return render_template("register.html", cities=CITIES)

    # POST: 处理注册
    dot_api_key = request.form.get("dot_api_key", "").strip()
    device_id = request.form.get("device_id", "").strip()
    city = request.form.get("city", "").strip()
    custom_lng = request.form.get("lng", "").strip()
    custom_lat = request.form.get("lat", "").strip()

    # 验证
    if not dot_api_key or not device_id:
        flash("请填写 Dot. API 密钥和设备序列号", "error")
        return render_template("register.html", cities=CITIES)

    # 解析城市坐标
    if city in CITIES:
        lng, lat = CITIES[city]
    elif custom_lng and custom_lat:
        try:
            lng = float(custom_lng)
            lat = float(custom_lat)
            city = city or "自定义位置"
        except ValueError:
            flash("经纬度格式不正确，请填写数字", "error")
            return render_template("register.html", cities=CITIES)
    else:
        flash("请选择城市或填写经纬度", "error")
        return render_template("register.html", cities=CITIES)

    # 保存订阅
    manage_token = db.add_subscription(dot_api_key, device_id, city, lng, lat)

    # 立即推送一次
    sub = db.get_subscription(manage_token)
    if sub:
        result = push_to_subscriber(sub)
        status = "success" if result["success"] else "failed"
        error_msg = None if result["success"] else result["message"]
        db.record_push(
            subscription_id=sub["id"],
            device_id=sub["device_id"],
            poem_title=result["poem_title"],
            poem_author=result["poem_author"],
            weather_desc=result["weather_desc"],
            temperature=result["temperature"],
            status=status,
            error_msg=error_msg,
        )
        if result["success"]:
            flash(f"注册成功！已为你推送第一条诗词天气：{result['poem_title']}", "success")
        else:
            flash(f"注册成功，但首次推送失败：{result['message']}。请检查 API 密钥和设备序列号是否正确。", "warning")
    else:
        flash("注册成功！", "success")

    return redirect(url_for("manage", token=manage_token))


@app.route("/manage/<token>", methods=["GET", "POST"])
def manage(token):
    """管理订阅页"""
    sub = db.get_subscription(token)
    if not sub:
        flash("订阅不存在或已失效", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update":
            city = request.form.get("city", "").strip()
            if city in CITIES:
                lng, lat = CITIES[city]
                db.update_subscription(token, city=city, lng=lng, lat=lat)
                flash(f"已更新城市为 {city}", "success")
            else:
                flash("请选择有效城市", "error")
            return redirect(url_for("manage", token=token))

        elif action == "push":
            # 手动触发推送
            result = push_to_subscriber(sub)
            status = "success" if result["success"] else "failed"
            error_msg = None if result["success"] else result["message"]
            db.record_push(
                subscription_id=sub["id"],
                device_id=sub["device_id"],
                poem_title=result["poem_title"],
                poem_author=result["poem_author"],
                weather_desc=result["weather_desc"],
                temperature=result["temperature"],
                status=status,
                error_msg=error_msg,
            )
            if result["success"]:
                flash(f"推送成功！{result['poem_title']} - {result['poem_author']}", "success")
            else:
                flash(f"推送失败：{result['message']}", "error")
            return redirect(url_for("manage", token=token))

        elif action == "delete":
            db.deactivate_subscription(token)
            flash("已取消订阅，感谢使用诗词天气", "info")
            return redirect(url_for("index"))

    # GET: 显示管理页
    history = db.get_push_history(token, limit=10)
    return render_template("manage.html", sub=sub, history=history, token=token, cities=CITIES)


@app.route("/api/cities")
def api_cities():
    """城市列表 API（供前端动态加载）"""
    return jsonify(CITIES)


# ── 启动 ──

def start_scheduler(app):
    """启动定时推送调度器"""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        push_all_subscribers,
        CronTrigger(hour=SERVICE_CONFIG["push_hour"], minute=SERVICE_CONFIG["push_minute"]),
        id="daily_push",
        replace_existing=True,
    )
    scheduler.start()
    print(f"定时推送已启动: 每天 {SERVICE_CONFIG['push_hour']:02d}:{SERVICE_CONFIG['push_minute']:02d}")
    return scheduler


def main():
    # 初始化数据库
    db.init_db()

    if not SERVICE_CONFIG["caiyun_token"]:
        print("警告: 未配置 caiyun_token，请在 config.json 或环境变量 CAIYUN_TOKEN 中设置")

    # 启动定时调度器
    start_scheduler(app)

    # 启动 Web 服务
    port = SERVICE_CONFIG["port"]
    print(f"诗词天气服务已启动: http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
