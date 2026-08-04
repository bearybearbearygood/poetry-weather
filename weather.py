"""彩云天气 API 客户端

数据来源：彩云天气 v2.6 API
功能：
  - 获取实时天气（温度、体感温度、湿度、风速、空气质量、舒适度）
  - 获取今日预报（最高温/最低温）
  - skycon 到天气类型映射
  - 温度/湿度触发逻辑（用于诗词匹配增强）
  - IP 自动定位（fallback）
"""

import urllib.request
import urllib.error
import json

# ── 彩云天气 skycon 到本地天气类型的映射 ──
# 彩云天气会返回带 _DAY / _NIGHT 后缀的值，统一映射
SKYCON_MAP = {
    "CLEAR": ("clear", "晴"),
    "CLEAR_DAY": ("clear", "晴"),
    "CLEAR_NIGHT": ("clear", "晴"),
    "PARTLY_CLOUDY": ("partly_cloudy", "多云"),
    "PARTLY_CLOUDY_DAY": ("partly_cloudy", "多云"),
    "PARTLY_CLOUDY_NIGHT": ("partly_cloudy", "多云"),
    "CLOUDY": ("cloudy", "阴"),
    "LIGHT_HAZE": ("haze", "轻度雾霾"),
    "MODERATE_HAZE": ("haze", "中度雾霾"),
    "HEAVY_HAZE": ("haze", "重度雾霾"),
    "LIGHT_RAIN": ("rain", "小雨"),
    "STABLE_RAIN": ("rain", "中雨"),
    "RAIN": ("rain", "雨"),
    "HEAVY_RAIN": ("heavy_rain", "大雨"),
    "STORM_RAIN": ("heavy_rain", "暴雨"),
    "LIGHT_SNOW": ("snow", "小雪"),
    "STABLE_SNOW": ("snow", "中雪"),
    "SNOW": ("snow", "雪"),
    "HEAVY_SNOW": ("heavy_snow", "大雪"),
    "STORM_SNOW": ("heavy_snow", "暴雪"),
    "FOG": ("fog", "雾"),
    "WIND": ("wind", "大风"),
    "DUST": ("dust", "浮尘"),
    "SAND": ("dust", "沙尘"),
    "HAIL": ("heavy_rain", "冰雹"),
    "SLEET": ("snow", "雨夹雪"),
}

# 天气图标 emoji
WEATHER_EMOJI = {
    "clear": "☀️",
    "partly_cloudy": "⛅",
    "cloudy": "☁️",
    "rain": "🌧️",
    "heavy_rain": "⛈️",
    "snow": "❄️",
    "heavy_snow": "🌨️",
    "fog": "🌫️",
    "haze": "😷",
    "wind": "🌬️",
    "dust": "🌪️",
    "hot": "🔥",
    "cold": "🥶",
}

# 舒适度描述
COMFORT_MAP = {
    0: "闷热",
    1: "酷热",
    2: "炎热",
    3: "热",
    4: "温暖",
    5: "舒适",
    6: "凉爽",
    7: "冷",
    8: "寒冷",
    9: "严寒",
}


def get_location_by_ip():
    """通过 IP 自动定位，返回经纬度

    使用 ip-api.com 免费接口（无需 key）。
    Returns:
        (lng, lat, city_name) 或 None
    """
    url = "http://ip-api.com/json/?lang=zh-CN&fields=status,lat,lon,city"
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") == "success":
            return data["lon"], data["lat"], data.get("city", "未知")
    except Exception:
        pass
    return None


def fetch_weather(caiyun_token, lng, lat):
    """从彩云天气 API 获取完整天气数据

    Args:
        caiyun_token: 彩云天气 API token
        lng: 经度
        lat: 纬度

    Returns:
        dict: 完整天气信息
    """
    url = (
        f"https://api.caiyunapp.com/v2.6/{caiyun_token}/{lng},{lat}/weather"
        f"?dailysteps=3&hourlysteps=48"
    )

    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"彩云天气 API 返回错误 {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接彩云天气 API: {e.reason}")

    if data.get("status") != "ok":
        raise RuntimeError(
            f"彩云天气 API 返回异常: {data.get('error', '未知错误')}"
        )

    result = data["result"]
    realtime = result.get("realtime", {})
    daily = result.get("daily", {})

    # ── skycon ──
    skycon = realtime.get("skycon", "CLEAR_DAY")
    category, description = SKYCON_MAP.get(skycon, ("clear", "晴"))
    emoji = WEATHER_EMOJI.get(category, "🌤️")

    # ── 温度 ──
    temperature = realtime.get("temperature")
    if temperature is not None:
        temperature = round(temperature)

    apparent_temp = realtime.get("apparent_temperature")
    if apparent_temp is not None:
        apparent_temp = round(apparent_temp)

    # 今日最高温/最低温
    temp_max = None
    temp_min = None
    if "temperature" in daily and daily["temperature"]:
        temp_max = round(daily["temperature"][0].get("max", 0))
        temp_min = round(daily["temperature"][0].get("min", 0))

    # ── 湿度 ──
    humidity = realtime.get("humidity")
    if humidity is not None:
        humidity = round(humidity * 100)

    # ── 风速 ──
    wind = realtime.get("wind", {})
    wind_speed = wind.get("speed")
    wind_direction = wind.get("direction")

    # ── 空气质量 ──
    air_quality = realtime.get("air_quality", {})
    aqi = air_quality.get("aqi", {})
    aqi_chn = aqi.get("chn")
    pm25 = air_quality.get("pm25")
    aqi_desc = air_quality.get("description", {}).get("chn", "")

    # ── 舒适度 ──
    comfort_index = None
    comfort_desc = ""
    life_index = realtime.get("life_index", {})
    if "comfort" in life_index:
        comfort_index = life_index["comfort"].get("index")
        comfort_desc = COMFORT_MAP.get(comfort_index, "")

    # ── 温度触发 ──
    triggers = [category]  # 基础天气类型

    if temperature is not None:
        if temperature >= 32:
            triggers.append("hot")
        elif temperature <= 5:
            triggers.append("cold")

    # 舒适度触发（补充温度判断）
    if comfort_index is not None:
        if comfort_index <= 3 and "hot" not in triggers:
            triggers.append("hot")
        elif comfort_index >= 7 and "cold" not in triggers:
            triggers.append("cold")

    # ── 湿度触发 ──
    if humidity is not None:
        if humidity >= 85 and category not in ("rain", "heavy_rain", "snow", "heavy_snow"):
            triggers.append("fog")  # 高湿度但没下雨 → 偏雾的感觉

    return {
        # 天气类型
        "category": category,
        "description": description,
        "emoji": emoji,
        "skycon": skycon,
        # 温度
        "temperature": temperature,
        "apparent_temp": apparent_temp,
        "temp_max": temp_max,
        "temp_min": temp_min,
        # 湿度
        "humidity": humidity,
        # 风
        "wind_speed": wind_speed,
        "wind_direction": wind_direction,
        # 空气质量
        "aqi": aqi_chn,
        "pm25": pm25,
        "aqi_desc": aqi_desc,
        # 舒适度
        "comfort_index": comfort_index,
        "comfort_desc": comfort_desc,
        # 触发列表（用于诗词匹配）
        "triggers": triggers,
    }
