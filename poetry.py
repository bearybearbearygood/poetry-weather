"""诗词匹配模块 - 从天气触发条件选择合适的古诗词

多维度匹配逻辑：
  1. 优先匹配更"特殊"的触发条件（hot/cold > 天气类型）
  2. 同一类别内优先选当季的诗
  3. 排除最近推送过的诗（去重）
"""

import json
import os
import random
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
POETRY_PATH = os.path.join(SCRIPT_DIR, "poetry.json")

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


def load_poetry():
    """读取诗词数据库"""
    with open(POETRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def select_poem(poetry_db, triggers, recent_titles=None):
    """从诗词库中选择一首诗

    Args:
        poetry_db: 诗词数据库
        triggers: 触发条件列表，如 ["clear", "hot"]
        recent_titles: 最近推送过的诗的标识集合（title|author）

    Returns:
        (poem, matched_trigger) 或 (None, None)
    """
    current_season = get_season()

    priority = {"hot": 0, "cold": 0, "heavy_rain": 1, "heavy_snow": 1,
                "dust": 2, "haze": 2, "fog": 2, "wind": 2,
                "rain": 3, "snow": 3, "cloudy": 4,
                "partly_cloudy": 5, "clear": 6}
    sorted_triggers = sorted(triggers, key=lambda t: priority.get(t, 99))

    if recent_titles is None:
        recent_titles = set()

    for trigger in sorted_triggers:
        poems = poetry_db.get(trigger, [])
        if not poems:
            continue

        seasonal = [p for p in poems if p.get("season") == current_season or p.get("season") == "all"]
        pool = seasonal if seasonal else poems

        available = [p for p in pool if f'{p.get("title", "")}|{p.get("author", "")}' not in recent_titles]
        if not available:
            available = pool

        return random.choice(available), trigger

    fallback = poetry_db.get("clear", poetry_db.get("rain", []))
    if fallback:
        return random.choice(fallback), "fallback"

    return None, None
