"""诗词匹配模块 - 从天气触发条件选择合适的古诗词

多维度匹配逻辑：
  1. 优先匹配更"特殊"的触发条件（hot/cold > 天气类型）
  2. 同一类别内优先选当季的诗
  3. 排除 dedup_days（默认20天）内推送过的诗（去重）
  4. 若某类池子全部在去重窗口内，选距上次推送最久的一首（LRU 兜底，避免连续重复）
"""

import json
import os
import random
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
POETRY_PATH = os.path.join(SCRIPT_DIR, "poetry.json")
POETRY_CI_PATH = os.path.join(SCRIPT_DIR, "poetry_ci.json")  # 预留位，未来扩展宋词版时取消注释

# 版本 → 诗词库路径映射
# 当前只提供 general（137 首通用古诗词库）。edition='ci' 会自动回退到 general 并打印警告。
# 未来增加宋词版时：把 poetry_ci.json 放回 scripts/ 目录，去掉 POETRY_CI_PATH 注释，并在 POETRY_PATHS 加 "ci": POETRY_CI_PATH
POETRY_PATHS = {
    "general": POETRY_PATH,
}

CATEGORY_NAMES = {
    "clear": "晴", "partly_cloudy": "多云", "cloudy": "阴",
    "rain": "雨", "heavy_rain": "大雨", "snow": "雪", "heavy_snow": "大雪",
    "fog": "雾", "haze": "霾", "wind": "大风", "dust": "沙尘",
    "hot": "高温", "cold": "严寒",
}

# 触发条件优先级：数值越小越优先（更"特殊"的天气类型优先匹配）
PRIORITY = {"hot": 0, "cold": 0, "heavy_rain": 1, "heavy_snow": 1,
            "dust": 2, "haze": 2, "fog": 2, "wind": 2,
            "rain": 3, "snow": 3, "cloudy": 4,
            "partly_cloudy": 5, "clear": 6}


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


def load_poetry(path=None, edition="general"):
    """读取诗词数据库

    Args:
        path: 可选 JSON 路径（指定时优先级高于 edition）
        edition: 版本，"general" (默认) 或 "ci"，仅在 path 为空时生效
    """
    if path is None:
        path = POETRY_PATHS.get(edition, POETRY_PATH)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def poem_key(poem):
    """诗词唯一标识（title|author）"""
    return f'{poem.get("title", "")}|{poem.get("author", "")}'


def days_since(last_sent, key):
    """返回某首诗距上次推送的天数；从未推送或时间解析失败返回 None（视为可推）"""
    ts = last_sent.get(key)
    if not ts:
        return None
    try:
        last = datetime.fromisoformat(ts)
        return (datetime.now() - last).days
    except (ValueError, TypeError):
        return None


def _in_window(pool, last_sent, dedup_days):
    """返回池中在去重窗口之外（可推送）的诗列表"""
    return [p for p in pool
            if (d := days_since(last_sent, poem_key(p))) is None or d >= dedup_days]


def _oldest(pool, last_sent):
    """返回池中距上次推送最久的一首（timestamp 最早）；无记录视为最早"""
    def ts(p):
        return last_sent.get(poem_key(p), "")
    return min(pool, key=ts)


def select_poem(poetry_db, triggers, last_sent=None, dedup_days=20, rng=None):
    """从诗词库中选择一首诗

    Args:
        poetry_db: 诗词数据库
        triggers: 触发条件列表，如 ["clear", "hot"]
        last_sent: {title|author: ISO 时间戳} 每首诗最近一次推送时间表
        dedup_days: 去重窗口天数，窗口内推送过的诗不会被选中
        rng: 可选 random.Random 实例（RSS 传种子 rng 保证确定性）；默认全局 random

    Returns:
        (poem, matched_trigger) 或 (None, None)
    """
    current_season = get_season()
    last_sent = last_sent or {}
    choice = rng.choice if rng else random.choice

    sorted_triggers = sorted(triggers, key=lambda t: PRIORITY.get(t, 99))

    for trigger in sorted_triggers:
        poems = poetry_db.get(trigger, [])
        if not poems:
            continue

        # 优先当季（含 all），无当季则用整池
        seasonal = [p for p in poems if p.get("season") == current_season or p.get("season") == "all"]
        pool = seasonal if seasonal else poems

        # 1) 去重窗口内可推的诗
        available = _in_window(pool, last_sent, dedup_days)
        if available:
            return choice(available), trigger

        # 2) 整池都在窗口内：选距上次推送最久的一首（保证至少不连续重复）
        return _oldest(pool, last_sent), trigger

    # 兜底
    fallback = poetry_db.get("clear", poetry_db.get("rain", []))
    if fallback:
        available = _in_window(fallback, last_sent, dedup_days)
        if available:
            return choice(available), "fallback"
        return _oldest(fallback, last_sent), "fallback"

    return None, None
