#!/usr/bin/env python3
"""Open-Meteo 天气客户端

替代彩云天气。特点：
  - 无需 API Key，全球覆盖
  - 数据开放（CC-BY-4.0），署名即可
  - 免费额度 10,000 次/天（非商业用途）

返回结构与 weather.fetch_weather 完全一致，调用方无需改动。
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

UA = "poetry-weather/1.0 (+https://github.com/bearybearbearygood/poetry-weather)"

# ── WMO Weather interpretation codes → 本地天气类型 ──
# https://open-meteo.com/en/docs
WMO_MAP = {
    0: ("clear", "晴"),
    1: ("partly_cloudy", "晴间多云"),
    2: ("partly_cloudy", "多云"),
    3: ("cloudy", "阴"),
    45: ("fog", "雾"),
    48: ("fog", "雾凇"),
    51: ("rain", "毛毛雨"),
    53: ("rain", "小雨"),
    55: ("rain", "细雨"),
    56: ("rain", "冻毛毛雨"),
    57: ("rain", "冻雨"),
    61: ("rain", "小雨"),
    63: ("rain", "中雨"),
    65: ("heavy_rain", "大雨"),
    66: ("rain", "冻雨"),
    67: ("heavy_rain", "强冻雨"),
    71: ("snow", "小雪"),
    73: ("snow", "中雪"),
    75: ("heavy_snow", "大雪"),
    77: ("snow", "米雪"),
    80: ("rain", "阵雨"),
    81: ("rain", "中阵雨"),
    82: ("heavy_rain", "强阵雨"),
    85: ("snow", "阵雪"),
    86: ("heavy_snow", "强阵雪"),
    95: ("heavy_rain", "雷阵雨"),
    96: ("heavy_rain", "雷暴伴冰雹"),
    99: ("heavy_rain", "强雷暴伴冰雹"),
}

# 严重度表，与 weather.py 保持一致
CATEGORY_SEVERITY = {
    "clear": 0, "partly_cloudy": 1, "cloudy": 2,
    "rain": 3, "snow": 3,
    "fog": 4, "haze": 4, "wind": 4, "dust": 4,
    "heavy_rain": 5, "heavy_snow": 5,
}

WEATHER_EMOJI = {
    "clear": "☀️", "partly_cloudy": "⛅", "cloudy": "☁️",
    "rain": "🌧️", "heavy_rain": "⛈️", "snow": "❄️",
    "heavy_snow": "🌨️", "fog": "🌫️", "haze": "😷",
    "wind": "🌬️", "dust": "🌪️",
}

# 体感温度 → 舒适度（对齐彩云 0~9 分级）
# 彩云的 comfort index 综合了体感温度与湿度，这里用体感温度近似；
# 0（闷热）需要湿度配合，下面 humidity 分支单独处理。
def _comfort_from_apparent(apparent):
    """体感温度 → 舒适度 0~9

    阈值刻意放宽了「冷」的门槛（4℃ 才算冷）：彩云的舒适度综合了湿度与风速，
    同温度下通常比纯体感更「温和」。若按线性映射，秋季 13℃ 就会落到「冷」，
    进而触发 cold 首日推寒诗，与体感不符。
    """
    if apparent is None:
        return None
    if apparent >= 35:
        return 1   # 酷热
    if apparent >= 31:
        return 2   # 炎热
    if apparent >= 28:
        return 3   # 热
    if apparent >= 25:
        return 4   # 温暖
    if apparent >= 20:
        return 5   # 舒适
    if apparent >= 14:
        return 6   # 凉爽
    if apparent >= 4:
        return 7   # 冷
    if apparent >= -6:
        return 8   # 寒冷
    return 9       # 严寒


COMFORT_MAP = {
    0: "闷热", 1: "酷热", 2: "炎热", 3: "热", 4: "温暖",
    5: "舒适", 6: "凉爽", 7: "冷", 8: "寒冷", 9: "严寒",
}

# pm2.5 (μg/m³) → 中国 AQI 等级描述（简化分级，够展示用）
def _aqi_desc_from_pm25(pm25):
    if pm25 is None:
        return "", None
    if pm25 <= 35:
        return "优", 1
    if pm25 <= 75:
        return "良", 2
    if pm25 <= 115:
        return "轻度污染", 3
    if pm25 <= 150:
        return "中度污染", 4
    if pm25 <= 250:
        return "重度污染", 5
    return "严重污染", 6


def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_air_quality(lng, lat, timeout=10):
    """空气质量（可选，失败不影响主流程）"""
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lng,
        "current": "pm2_5,pm10,dust",
        "timezone": "Asia/Shanghai",
    })
    try:
        data = _get_json(f"https://air-quality-api.open-meteo.com/v1/air-quality?{params}", timeout)
    except Exception:
        return {"pm25": None, "pm10": None, "dust": None, "aqi_desc": "", "aqi_level": None}

    cur = data.get("current") or {}
    pm25 = cur.get("pm2_5")
    desc, level = _aqi_desc_from_pm25(pm25)
    return {
        "pm25": round(pm25, 1) if pm25 is not None else None,
        "pm10": round(cur["pm10"], 1) if cur.get("pm10") is not None else None,
        "dust": cur.get("dust"),
        "aqi_desc": desc,
        "aqi_level": level,
    }


def fetch_weather(lng, lat, timeout=15):
    """获取完整天气数据，返回结构与 weather.fetch_weather 一致"""
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lng,
        "current": ",".join([
            "temperature_2m", "relative_humidity_2m", "apparent_temperature",
            "weather_code", "cloud_cover", "pressure_msl",
            "wind_speed_10m", "wind_direction_10m", "precipitation",
        ]),
        "daily": ",".join([
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "sunrise", "sunset", "uv_index_max", "precipitation_sum",
        ]),
        "hourly": "visibility",
        "timezone": "Asia/Shanghai",
        "forecast_days": 1,
        "wind_speed_unit": "ms",
    })
    url = f"https://api.open-meteo.com/v1/forecast?{params}"

    try:
        data = _get_json(url, timeout)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Open-Meteo API 返回错误 {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接 Open-Meteo API: {e.reason}")

    cur = data.get("current") or {}
    daily = data.get("daily") or {}

    # ── 天气类型：当前 + 全天预报取更恶劣者 ──
    # 与彩云实现同一口径：雷阵雨来临前，当前时刻可能还是晴，全天预报已是雷雨
    code_now = cur.get("weather_code")
    cat_now, desc_now = WMO_MAP.get(code_now, ("clear", "晴"))

    daily_codes = daily.get("weather_code") or []
    candidates = [(CATEGORY_SEVERITY.get(cat_now, 0), 0, cat_now, desc_now)]
    forecast_code = None
    if daily_codes:
        forecast_code = daily_codes[0]
        fc_cat, fc_desc = WMO_MAP.get(forecast_code, (None, None))
        if fc_cat:
            candidates.append((CATEGORY_SEVERITY.get(fc_cat, 0), 1, fc_cat, fc_desc))

    severity, _, category, description = max(candidates, key=lambda c: (c[0], -c[1]))

    # ── 温度 ──
    temperature = cur.get("temperature_2m")
    temperature = round(temperature) if temperature is not None else None

    apparent_temp = cur.get("apparent_temperature")
    apparent_temp = round(apparent_temp) if apparent_temp is not None else None

    temp_max = temp_min = None
    if daily.get("temperature_2m_max"):
        temp_max = round(daily["temperature_2m_max"][0])
    if daily.get("temperature_2m_min"):
        temp_min = round(daily["temperature_2m_min"][0])

    # ── 湿度 ──
    humidity = cur.get("relative_humidity_2m")
    humidity = round(humidity) if humidity is not None else None

    # ── 风（已在请求里指定 m/s）──
    wind_speed = cur.get("wind_speed_10m")
    wind_speed = round(wind_speed, 1) if wind_speed is not None else None
    wind_speed_kmh = round(wind_speed * 3.6, 1) if wind_speed is not None else None
    wind_direction = cur.get("wind_direction_10m")

    # ── 气压 / 云量 / 降水 / 能见度 ──
    pressure = cur.get("pressure_msl")
    pressure = round(pressure) if pressure is not None else None

    cloudrate = cur.get("cloud_cover")
    cloudrate = round(cloudrate) if cloudrate is not None else None

    precipitation = cur.get("precipitation")
    precip_intensity = precipitation if precipitation is not None else 0
    precip_status = "降水" if precip_intensity and precip_intensity > 0 else "无降水"

    visibility = None
    hourly_vis = (data.get("hourly") or {}).get("visibility") or []
    if hourly_vis:
        vals = [v for v in hourly_vis if v is not None]
        if vals:
            visibility = round(vals[0] / 1000, 1)  # m → km

    # ── 日出日落 ──
    sunrise = (daily.get("sunrise") or [""])[0]
    sunset = (daily.get("sunset") or [""])[0]

    # ── 空气质量 ──
    air = fetch_air_quality(lng, lat, timeout=8)
    aqi_desc = air["aqi_desc"]
    pm25 = air["pm25"]

    # ── 附加天气类型：霾 / 沙尘 / 大风 ──
    # Open-Meteo 的 weather_code 不含这几类，只能靠空气质量与风速补判。
    # 仅在原本是晴/多云/阴时升级，避免把雨天判成霾天。
    if category in ("clear", "partly_cloudy", "cloudy"):
        if air.get("dust") is not None and air["dust"] >= 200:
            category, description = "dust", "沙尘"
        elif pm25 is not None and pm25 > 75:
            if pm25 <= 115:
                category, description = "haze", "轻度雾霾"
            elif pm25 <= 150:
                category, description = "haze", "中度雾霾"
            else:
                category, description = "haze", "重度雾霾"
        elif wind_speed is not None and wind_speed >= 10.8:  # 6 级风
            category, description = "wind", "大风"

    emoji = WEATHER_EMOJI.get(category, "🌤️")

    # ── 舒适度 ──
    comfort_index = _comfort_from_apparent(
        cur.get("apparent_temperature")
    )
    # 高温 + 高湿 = 闷热
    if (
        comfort_index is not None and 0 <= comfort_index <= 4
        and humidity is not None and humidity >= 80
    ):
        comfort_index = 0
    comfort_desc = COMFORT_MAP.get(comfort_index, "") if comfort_index is not None else ""

    # ── 紫外线（全天峰值）──
    uv_index = None
    uv_values = daily.get("uv_index_max") or []
    if uv_values and uv_values[0] is not None:
        uv_index = round(uv_values[0], 1)

    ultraviolet_desc = ""
    if uv_index is not None:
        if uv_index < 3:
            ultraviolet_desc = "弱"
        elif uv_index < 6:
            ultraviolet_desc = "中等"
        elif uv_index < 8:
            ultraviolet_desc = "强"
        else:
            ultraviolet_desc = "很强"

    # ── 触发列表（阈值与 weather.py 保持一致）──
    triggers = [category]

    if temperature is not None:
        if temperature >= 32:
            triggers.append("hot")
        elif temperature <= 5:
            triggers.append("cold")

    if comfort_index is not None:
        if comfort_index <= 2 and "hot" not in triggers:
            triggers.append("hot")
        elif comfort_index >= 7 and "cold" not in triggers:
            triggers.append("cold")

    if humidity is not None:
        if (
            humidity >= 92
            and category not in ("rain", "heavy_rain", "snow", "heavy_snow", "clear", "partly_cloudy", "cloudy")
        ):
            triggers.append("fog")

    return {
        "category": category,
        "description": description,
        "emoji": emoji,
        "skycon": f"WMO_{code_now}",
        "realtime_category": cat_now,
        "forecast_skycon": f"WMO_{forecast_code}" if forecast_code is not None else None,
        "temperature": temperature,
        "apparent_temp": apparent_temp,
        "temp_max": temp_max,
        "temp_min": temp_min,
        "humidity": humidity,
        "wind_speed": wind_speed,
        "wind_speed_kmh": wind_speed_kmh,
        "wind_direction": wind_direction,
        "pressure": pressure,
        "visibility": visibility,
        "cloudrate": cloudrate,
        "precip_intensity": precip_intensity,
        "precip_status": precip_status,
        "sunrise": sunrise,
        "sunset": sunset,
        "aqi": None,          # Open-Meteo 只给 pm2.5，不给 CN AQI 数值
        "pm25": pm25,
        "aqi_desc": aqi_desc,
        "comfort_index": comfort_index,
        "comfort_desc": comfort_desc,
        "uv_index": uv_index,
        "uv_desc": ultraviolet_desc,
        "ultraviolet_desc": ultraviolet_desc,
        "triggers": triggers,
        "source": "open-meteo",
    }


if __name__ == "__main__":
    import sys

    args = sys.argv[1:] or ["116.4074", "39.9042"]
    lng, lat = float(args[0]), float(args[1])
    result = fetch_weather(lng, lat)
    print(json.dumps(result, ensure_ascii=False, indent=1))
