"""Dot. 墨水屏设备 API 客户端

使用 Text API（比 Canvas API 更简单可靠，由 Dot. 设备端渲染）：

布局效果（296x152px 墨水屏）：
┌─────────────────────────────────┐
│  26~36℃ 晴 热                    │ ← 标题：温度区间+天气+舒适度
│                                 │
│  永日不可暮，                      │ ← 正文：诗句
│  炎蒸毒我肠。                      │
│  ——杜甫《夏夜叹》                 │ ← 出处
│                                 │
│  湿度77% 风速3级 空气优 · 8月4日   │ ← 签名：天气详情+日期
└─────────────────────────────────┘
"""

import urllib.request
import urllib.error
import json

DOT_API_BASE = "https://dot.mindreset.tech"


def build_text_payload(poem, weather, date_str):
    """构建 Text API 的请求体

    天气为主标题，诗词为正文，天气详情+日期为签名。

    Args:
        poem: 诗词字典（title, dynasty, author, lines）
        weather: 天气字典（description, temperature, humidity 等）
        date_str: 日期字符串，如 "8月4日 周二"
    """
    # ── 标题：温度区间 + 天气状况 + 舒适度 ──
    temp_min = weather.get("temp_min")
    temp_max = weather.get("temp_max")
    title_parts = []
    if temp_min is not None and temp_max is not None:
        title_parts.append(f"{temp_min}~{temp_max}℃")
    elif weather.get("temperature") is not None:
        title_parts.append(f'{weather["temperature"]}℃')
    if weather.get("description"):
        title_parts.append(weather["description"])
    if weather.get("comfort_desc"):
        title_parts.append(weather["comfort_desc"])
    title = " ".join(title_parts)

    # ── 正文：诗句 + 出处 ──
    poem_lines = poem.get("lines", [])
    poem_text = "\n".join(poem_lines)
    author = poem.get("author", "")
    poem_title = poem.get("title", "无题")
    source = f"\n——{author}《{poem_title}》" if author else f"\n——《{poem_title}》"
    message = poem_text + source

    # ── 签名：天气详情 + 日期 ──
    sig_parts = []
    if weather.get("humidity") is not None:
        sig_parts.append(f'湿度{weather["humidity"]}%')
    if weather.get("wind_speed") is not None:
        wind = round(weather["wind_speed"])
        sig_parts.append(f"风速{wind}m/s")
    if weather.get("aqi") is not None and weather.get("aqi_desc"):
        sig_parts.append(f'空气{weather["aqi_desc"]}')
    elif weather.get("aqi") is not None:
        sig_parts.append(f'AQI{weather["aqi"]}')
    sig_parts.append(date_str)
    signature = " · ".join(sig_parts)

    payload = {
        "refreshNow": True,
        "title": title,
        "message": message,
        "signature": signature,
        "styles": {
            "title": {
                "fontFamily": "ChillDuanSans",
                "fontSize": 24,
                "fontWeight": 700
            },
            "message": {
                "fontFamily": "ChillDuanSans",
                "fontSize": 16,
                "lineHeight": 1.4
            },
            "signature": {
                "fontFamily": "ChillDuanSans",
                "fontSize": 12
            }
        }
    }

    return payload


def get_text_api_task_key(dot_api_key, device_id):
    """查询设备循环中的 TEXT_API 内容的 taskKey

    Returns:
        str or None: taskKey，如果没有则返回 None
    """
    url = f"{DOT_API_BASE}/api/authV2/open/device/{device_id}/loop/list"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {dot_api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data:
            if item.get("type") == "TEXT_API":
                return item.get("key")
    except Exception:
        pass
    return None


def push_to_device(dot_api_key, device_id, poem, weather, date_str):
    """通过 Text API 推送诗词到 Dot. 设备

    自动查询并携带 taskKey，确保精准覆盖已有文本内容。

    Args:
        dot_api_key: Dot. API 密钥
        device_id: 设备序列号
        poem: 诗词字典
        weather: 天气字典
        date_str: 日期字符串

    Returns:
        str: API 返回的消息
    """
    payload = build_text_payload(poem, weather, date_str)

    # 查询已有的 TEXT_API taskKey，精准覆盖
    task_key = get_text_api_task_key(dot_api_key, device_id)
    if task_key:
        payload["taskKey"] = task_key

    url = f"{DOT_API_BASE}/api/authV2/open/device/{device_id}/text"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {dot_api_key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("message", "推送成功")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        try:
            error_msg = json.loads(error_body).get("message", error_body)
        except (json.JSONDecodeError, ValueError):
            error_msg = error_body or e.reason
        raise RuntimeError(f"Dot. API 错误 {e.code}: {error_msg}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接 Dot. API: {e.reason}")
