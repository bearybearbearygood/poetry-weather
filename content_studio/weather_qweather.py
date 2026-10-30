#!/usr/bin/env python3
"""和风天气客户端（QWeather）

与 Dot 内容工坊里的官方天气内容同源，保证同一城市、同一时刻两边数据一致。

鉴权方式：JWT（EdDSA / Ed25519）
  - Header: {"alg":"EdDSA","kid":<Credential ID>}
  - Payload: {"iss":<开发者ID>,"sub":<项目ID>,"iat":now-30,"exp":now+900}
  - 私钥本地保管，公钥上传到控制台创建凭据

两个坑：
  1. 必须走账号专属 API Host（xxxxx.re.qweatherapi.com），公共域名会返回 Invalid Host
  2. 返回体是 gzip 压缩，不解压会得到乱码

返回结构与 weather.py 的 fetch_weather 一致，上层无需区分数据源。
"""

import base64
import gzip
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.serialization import load_pem_private_key

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_KEY_PATH = os.path.join(SCRIPT_DIR, "secrets", "ed25519-private.pem")

UA = "poetry-weather/1.0 (+https://github.com/bearybearbearygood/poetry-weather)"

CST = timezone(timedelta(hours=8))

# ── 天气代码 → 本地 13 类 ──
# 来源：https://dev.qweather.com/docs/api/weather/weather-conditions/（54 个代码）
CODE_MAP = {
    "100": ("clear", "晴"),

    "101": ("partly_cloudy", "多云"),
    "102": ("partly_cloudy", "少云"),
    "103": ("partly_cloudy", "晴间多云"),

    "104": ("cloudy", "阴"),

    "300": ("rain", "阵雨"),
    "305": ("rain", "小雨"),
    "306": ("rain", "中雨"),
    "309": ("rain", "毛毛雨"),
    "313": ("rain", "冻雨"),
    "314": ("rain", "小到中雨"),
    "315": ("rain", "中到大雨"),
    "399": ("rain", "雨"),

    "301": ("heavy_rain", "强阵雨"),
    "302": ("heavy_rain", "雷阵雨"),
    "303": ("heavy_rain", "强雷阵雨"),
    "304": ("heavy_rain", "雷阵雨伴冰雹"),
    "307": ("heavy_rain", "大雨"),
    "308": ("heavy_rain", "极端降雨"),
    "310": ("heavy_rain", "暴雨"),
    "311": ("heavy_rain", "大暴雨"),
    "312": ("heavy_rain", "特大暴雨"),
    "316": ("heavy_rain", "大到暴雨"),
    "317": ("heavy_rain", "暴雨到大暴雨"),
    "318": ("heavy_rain", "大暴雨到特大暴雨"),

    "400": ("snow", "小雪"),
    "401": ("snow", "中雪"),
    "404": ("snow", "雨夹雪"),
    "405": ("snow", "雨雪"),
    "406": ("snow", "阵雨夹雪"),
    "407": ("snow", "阵雪"),
    "408": ("snow", "小到中雪"),
    "499": ("snow", "雪"),

    "402": ("heavy_snow", "大雪"),
    "403": ("heavy_snow", "暴雪"),
    "409": ("heavy_snow", "中到大雪"),
    "410": ("heavy_snow", "大到暴雪"),

    "500": ("fog", "薄雾"),
    "501": ("fog", "雾"),
    "509": ("fog", "浓雾"),
    "510": ("fog", "强浓雾"),
    "514": ("fog", "大雾"),
    "515": ("fog", "特强浓雾"),

    "502": ("haze", "霾"),
    "511": ("haze", "中度霾"),
    "512": ("haze", "重度霾"),
    "513": ("haze", "严重霾"),

    "503": ("dust", "扬沙"),
    "504": ("dust", "浮尘"),
    "507": ("dust", "沙尘暴"),
    "508": ("dust", "强沙尘暴"),
}

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
    "wind": "🌬️", "dust": "🌪️", "hot": "🔥", "cold": "🥶",
}

# 和风的舒适度指数是 1~11 级 + 文字，与彩云的 0~9 数字体系不同。
# 不硬做换算，直接用文字判断该不该触发高温/严寒，避免两套体系对不上。
HOT_WORDS = ("较热", "很热", "炎热", "酷热", "闷热")
COLD_WORDS = ("较冷", "很冷", "寒冷", "酷冷")
# 和风还会给「不舒适」这种中性词，不带冷热倾向，只能结合温度判断
NEUTRAL_BAD = ("不舒适", "很不舒适")

_token_lock = threading.Lock()
_token_cache = {"value": None, "exp": 0}


def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


class QWeather:
    def __init__(self, host=None, kid=None, sub=None, iss=None, key_path=None):
        self.host = host or os.environ.get("QWEATHER_HOST", "")
        self.kid = kid or os.environ.get("QWEATHER_KID", "")
        self.sub = sub or os.environ.get("QWEATHER_SUB", "")
        self.iss = iss or os.environ.get("QWEATHER_ISS", "")
        self.key_path = key_path or os.environ.get("QWEATHER_KEY_PATH", DEFAULT_KEY_PATH)
        self._key = None

    def _private_key(self):
        """优先读环境变量，其次读文件

        部署到云主机时私钥不能跟着仓库走，用 QWEATHER_PRIVATE_KEY 传整段 PEM 内容；
        本地开发则直接读 secrets/ed25519-private.pem。
        """
        if self._key is None:
            pem = os.environ.get("QWEATHER_PRIVATE_KEY", "").strip()
            if pem:
                self._key = load_pem_private_key(pem.encode(), password=None)
            else:
                with open(self.key_path, "rb") as f:
                    self._key = load_pem_private_key(f.read(), password=None)
        return self._key

    def token(self):
        """签发 JWT，15 分钟内复用"""
        now = int(time.time())
        with _token_lock:
            if _token_cache["value"] and _token_cache["exp"] > now + 60:
                return _token_cache["value"]

            header = {"alg": "EdDSA", "kid": self.kid}
            payload = {
                "iss": self.iss,
                "sub": self.sub,
                "iat": now - 30,   # 官方建议回拨 30 秒，防止时钟误差
                "exp": now + 900,
            }
            signing = (
                _b64url(json.dumps(header, separators=(",", ":")).encode())
                + b"."
                + _b64url(json.dumps(payload, separators=(",", ":")).encode())
            )
            signature = _b64url(self._private_key().sign(signing))
            value = (signing + b"." + signature).decode()

            _token_cache["value"] = value
            _token_cache["exp"] = now + 900
            return value

    def get(self, path, timeout=15):
        url = f"https://{self.host}{path}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.token()}",
            "Accept-Encoding": "gzip",
            "User-Agent": UA,
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read()
            if e.headers.get("Content-Encoding") == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass
            detail = raw.decode("utf-8", errors="ignore")[:200]
            raise RuntimeError(f"和风天气 API {e.code}: {detail}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"无法连接和风天气 API: {e.reason}")


def _local_hhmm(iso_utc):
    """'2026-10-29T22:40Z' → '06:40'（东八区）"""
    if not iso_utc:
        return ""
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
        return dt.astimezone(CST).strftime("%H:%M")
    except (ValueError, AttributeError):
        return ""


def fetch_weather(lng, lat, client=None):
    """取一地完整天气，结构与 weather.fetch_weather 一致"""
    c = client or QWeather()
    loc = f"{lng:.4f},{lat:.4f}"

    cur = c.get(f"/weather/v1/current/{lat:.4f}/{lng:.4f}")
    daily = c.get(f"/weather/v1/daily/{lat:.4f}/{lng:.4f}?days=1")

    # 空气质量与生活指数是加分项，失败不影响主流程
    try:
        air = c.get(f"/airquality/v1/current/{lat:.4f}/{lng:.4f}")
    except RuntimeError:
        air = {}
    try:
        idx = c.get(f"/v7/indices/1d?location={urllib.parse.quote(loc)}&type=5,8")
    except RuntimeError:
        idx = {}

    # ── 天气类型 ──
    cond = cur.get("condition") or {}
    code = str(cond.get("code", ""))
    category, description = CODE_MAP.get(code, ("clear", cond.get("text") or "晴"))

    # 当前与全天取更恶劣者：雷雨来临前，此刻可能还是晴
    day = (daily.get("days") or [{}])[0]
    # 全天天气代码在 daytime / nighttime 子对象里，day 顶层没有
    day_cond = (day.get("daytime") or {}).get("condition") or \
               (day.get("nighttime") or {}).get("condition") or {}
    day_code = str(day_cond.get("code", ""))
    if day_code in CODE_MAP:
        d_cat, d_desc = CODE_MAP[day_code]
        if CATEGORY_SEVERITY.get(d_cat, 0) > CATEGORY_SEVERITY.get(category, 0):
            category, description = d_cat, d_desc

    # 特殊代码
    if code == "900":
        category, description = "clear", "热"
    elif code == "901":
        category, description = "clear", "冷"

    # ── 数值 ──
    def val(obj, key="value"):
        if isinstance(obj, dict):
            v = obj.get(key)
            return v
        return None

    temperature = val(cur.get("temperature"))
    temperature = round(temperature) if temperature is not None else None

    apparent = val(cur.get("feelsLike"))
    apparent = round(apparent) if apparent is not None else None

    temp_max = val(day.get("temperatureMax"))
    temp_min = val(day.get("temperatureMin"))
    temp_max = round(temp_max) if temp_max is not None else None
    temp_min = round(temp_min) if temp_min is not None else None

    humidity = cur.get("humidity")
    humidity = round(humidity * 100) if humidity is not None else None

    wind = cur.get("wind") or {}
    wind_speed = val(wind.get("speed"))
    wind_speed = round(wind_speed, 1) if wind_speed is not None else None
    wind_scale = wind.get("scale")
    wind_speed_kmh = round(wind_speed * 3.6, 1) if wind_speed is not None else None
    wind_dir = (wind.get("direction") or {}).get("degree")

    pressure = val(cur.get("pressure"))
    pressure = round(pressure) if pressure is not None else None

    vis = val(cur.get("visibility"))
    visibility = round(vis / 1000, 1) if vis is not None else None

    cloud = cur.get("cloudCover")
    cloudrate = round(cloud) if cloud is not None else None

    precip = val((cur.get("precipitation") or {}).get("amount"))
    precip_intensity = precip if precip is not None else 0
    precip_status = "降水" if precip_intensity and precip_intensity > 0 else "无降水"

    astro = day.get("astro") or {}
    sunrise = _local_hhmm(astro.get("sunrise"))
    sunset = _local_hhmm(astro.get("sunset"))

    # ── 空气质量 ──
    aqi_value = None
    aqi_desc = ""
    pm25 = None
    for item in air.get("indexes") or []:
        if item.get("code") == "cn-mee":
            aqi_value = item.get("aqi")
            aqi_desc = item.get("category", "")
            break
    for p in air.get("pollutants") or []:
        if p.get("code") == "pm2p5":
            pm25 = val(p.get("concentration"))
            break

    # ── 生活指数 ──
    comfort_level = None
    comfort_desc = ""
    uv_level = ""
    for item in idx.get("daily") or []:
        if item.get("type") == "8":
            comfort_desc = item.get("category", "")
            try:
                comfort_level = int(item.get("level"))
            except (TypeError, ValueError):
                comfort_level = None
        elif item.get("type") == "5":
            uv_level = item.get("category", "")

    uv_index = day.get("uvIndexMax")
    if uv_index is None:
        uv_index = cur.get("uvIndex")
    ultraviolet_desc = uv_level
    if not ultraviolet_desc and uv_index is not None:
        if uv_index < 3:
            ultraviolet_desc = "弱"
        elif uv_index < 6:
            ultraviolet_desc = "中等"
        elif uv_index < 8:
            ultraviolet_desc = "强"
        else:
            ultraviolet_desc = "很强"

    # ── 触发 ──
    triggers = [category]

    if temperature is not None:
        if temperature >= 32:
            triggers.append("hot")
        elif temperature <= 5:
            triggers.append("cold")

    if comfort_desc:
        if any(w in comfort_desc for w in HOT_WORDS):
            if "hot" not in triggers:
                triggers.append("hot")
        elif any(w in comfort_desc for w in COLD_WORDS):
            if "cold" not in triggers:
                triggers.append("cold")
        elif any(w in comfort_desc for w in NEUTRAL_BAD) and temperature is not None:
            # 「不舒适」本身不指明方向，用温度补判
            if temperature >= 28 and "hot" not in triggers:
                triggers.append("hot")
            elif temperature <= 8 and "cold" not in triggers:
                triggers.append("cold")

    if humidity is not None and humidity >= 92:
        if category not in ("rain", "heavy_rain", "snow", "heavy_snow",
                            "clear", "partly_cloudy", "cloudy"):
            triggers.append("fog")

    return {
        "category": category,
        "description": description,
        "emoji": WEATHER_EMOJI.get(category, "🌤️"),
        "skycon": f"QW_{code}",
        "realtime_category": category,
        "forecast_skycon": f"QW_{day_code}" if day_code else None,
        "temperature": temperature,
        "apparent_temp": apparent,
        "temp_max": temp_max,
        "temp_min": temp_min,
        "humidity": humidity,
        "wind_speed": wind_speed,
        "wind_speed_kmh": wind_speed_kmh,
        "wind_direction": wind_dir,
        "wind_scale": wind_scale,
        "pressure": pressure,
        "visibility": visibility,
        "cloudrate": cloudrate,
        "precip_intensity": precip_intensity,
        "precip_status": precip_status,
        "sunrise": sunrise,
        "sunset": sunset,
        "aqi": aqi_value,
        "pm25": pm25,
        "aqi_desc": aqi_desc,
        "comfort_index": comfort_level,
        "comfort_desc": comfort_desc,
        "uv_index": uv_index,
        "uv_desc": ultraviolet_desc,
        "ultraviolet_desc": ultraviolet_desc,
        "triggers": triggers,
        "source": "qweather",
    }


if __name__ == "__main__":
    import sys

    args = sys.argv[1:] or ["116.4074", "39.9042"]
    lng, lat = float(args[0]), float(args[1])
    print(json.dumps(fetch_weather(lng, lat), ensure_ascii=False, indent=1))
