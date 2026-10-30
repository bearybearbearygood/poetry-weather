#!/usr/bin/env python3
"""城市名 → 经纬度解析

用于「用户自己填城市」的场景（内容工坊 REST API 通道 / RSS 的 ?city=）。

解析优先级：
  1. cities.json      手工维护的常用表（最快，无网络请求）
  2. cities_cn.json   全国城市表（可选，存在则加载）
  3. Open-Meteo Geocoding  兜底，与天气数据同源，免 key、支持中文

为什么不用 OSM Nominatim：它是境外服务且限速严格（1 req/s），
一旦被 Dot 侧定时调用很容易失败。Open-Meteo 与天气 API 同一家，
少一个外部依赖，中文解析质量也更好。

注意：不要无脑截断行政后缀。辽宁有「朝阳市」，北京有「朝阳区」，
去后缀会撞车，所以精确匹配永远优先，候选名只作为后续尝试。
"""

import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CITIES_PATH = os.path.join(SCRIPT_DIR, "cities.json")
CITIES_CN_PATH = os.path.join(SCRIPT_DIR, "cities_cn.json")
CACHE_PATH = os.path.join(SCRIPT_DIR, "geocode_cache.json")

UA = "poetry-weather/1.0 (+https://github.com/bearybearbearygood/poetry-weather)"

SUFFIXES = ("特别行政区", "自治区", "自治州", "地区", "市辖区", "市", "区", "县", "旗", "盟")

_lock = threading.Lock()
_cache = {}            # 进程内缓存
_local_tables = None   # 惰性加载的本地表


def _load_local_tables():
    global _local_tables
    if _local_tables is not None:
        return _local_tables

    table = {}
    for path in (CITIES_CN_PATH, CITIES_PATH):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for name, coord in data.items():
            if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                try:
                    table[name] = (float(coord[0]), float(coord[1]))
                except (TypeError, ValueError):
                    continue

    _local_tables = table
    return table


def _candidates(name):
    """生成候选名，精确优先"""
    raw = re.sub(r"\s+", "", name.strip())
    if not raw:
        return
    yield raw
    for suf in SUFFIXES:
        if raw.endswith(suf) and len(raw) - len(suf) >= 2:
            yield raw[: -len(suf)]
            break


def _lookup_local(name):
    table = _load_local_tables()
    for cand in _candidates(name):
        if cand in table:
            lng, lat = table[cand]
            return {"lng": lng, "lat": lat, "name": cand, "source": "local"}
    return None


def _load_disk_cache():
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_disk_cache(entry):
    """把新解析结果落盘，减少对外部服务的重复请求"""
    try:
        data = _load_disk_cache()
        data.update(entry)
        # 只保留最近 2000 条，避免文件无限增长
        if len(data) > 2000:
            data = dict(list(data.items())[-2000:])
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=0)
    except Exception:
        pass


def _remote_candidates(name):
    """远端查询用的候选名

    与本地表不同：区县级不做去后缀降级。Open-Meteo 的中国数据只到市镇级，
    把「朝阳区」截成「朝阳」会匹配到重庆的一个村，比解析失败更糟。
    """
    raw = re.sub(r"\s+", "", name.strip())
    if not raw:
        return
    yield raw
    if raw.endswith(("区", "县", "旗")):
        return
    for suf in SUFFIXES:
        if raw.endswith(suf) and len(raw) - len(suf) >= 2:
            yield raw[: -len(suf)]
            break


# 行政级别优先级：首都 > 省会 > 地级市 > 县级 > 一般居民点
FEATURE_PRIORITY = {"PPLC": 0, "PPLA": 1, "PPLA2": 2, "PPLA3": 3, "PPLA4": 4}


def _lookup_openmeteo(name):
    """Open-Meteo Geocoding，只接受中国境内结果"""
    for cand in _remote_candidates(name):
        params = urllib.parse.urlencode({
            "name": cand,
            "count": 10,
            "language": "zh",
            "format": "json",
        })
        url = f"https://geocoding-api.open-meteo.com/v1/search?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            continue

        results = data.get("results") or []
        cn = [r for r in results if r.get("country_code") == "CN"]
        if not cn:
            continue

        # 同名地点很多（如「杭州」在浙江与陕西各有一个）：
        # 先按行政级别、再按人口排，取最符合直觉的那个。
        cn.sort(key=lambda r: (
            FEATURE_PRIORITY.get(r.get("feature_code"), 9),
            -(r.get("population") or 0),
        ))
        hit = cn[0]

        try:
            lat = float(hit["latitude"])
            lng = float(hit["longitude"])
        except (KeyError, TypeError, ValueError):
            continue

        if not (3.0 <= lat <= 54.0 and 73.0 <= lng <= 136.0):
            continue

        display = hit.get("name") or cand
        for suf in SUFFIXES:
            if display.endswith(suf) and len(display) - len(suf) >= 2:
                display = display[: -len(suf)]
                break

        return {
            "lng": lng,
            "lat": lat,
            "name": display,
            "source": "open-meteo",
            "admin1": hit.get("admin1", ""),
        }
    return None


def resolve_city(name, allow_remote=True):
    """城市名 → {lng, lat, name, source}；解析不了返回 None

    allow_remote=False 时只查本地表（离线/测试用）。
    """
    if not name or not name.strip():
        return None

    key = name.strip()

    with _lock:
        if key in _cache:
            return _cache[key]

    disk = _load_disk_cache()
    if key in disk:
        hit = disk[key]
        with _lock:
            _cache[key] = hit
        return hit

    result = _lookup_local(key)

    if result is None and allow_remote:
        result = _lookup_openmeteo(key)
        if result is not None:
            _save_disk_cache({key: result})

    with _lock:
        _cache[key] = result
    return result


def clear_cache():
    with _lock:
        _cache.clear()


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:] or ["北京", "杭州市", "喀什", "朝阳区", "三亚市", "不存在城市xyz"]:
        print(arg, "->", resolve_city(arg))
