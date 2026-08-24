"""Dot. 墨水屏设备 API 客户端 — Image API 版

用 Pillow 生成 296×152 图片，像素级控制排版：
- 诗词真正居中（textbbox 测量宽度后计算 x 坐标，五言七言都能对齐）
- 无衬线字体（冬青黑体）+ 假粗体（水平/垂直偏移重绘，增粗约1.5倍），墨水屏竖画清晰且不糊
- 每行独立字号：诗 20px、出处 16px、签名 14px、顶部 16px
- 底部右对齐
- 底部显示日期+农历，节气当天追加节气名
- base64 PNG 推送到 Dot. Image API

布局效果（296×152px）：
┌─────────────────────────────────┐
│ 24~26℃ 湿度95% 阴 空气优        │ ← 顶部 16px 左对齐
│                                 │
│       永日不可暮，              │ ← 诗词 20px 居中
│       炎蒸毒我肠。              │ ← 诗词 20px 居中
│      ——杜甫《夏夜叹》           │ ← 出处 16px 居中
│                                 │
│  8月7日 · 周三 · 农历七月初五 · 立秋   │ ← 底部 14px 右对齐
└─────────────────────────────────┘

注：体感属性（热/寒冷）不显示，但 triggers 仍保留给诗词匹配用。
"""

import urllib.request
import urllib.error
import json
import base64
import io
import os
from datetime import date

from PIL import Image, ImageDraw, ImageFont
from lunardate import LunarDate
from lunar_python import Solar as _LunarSolar

DOT_API_BASE = "https://dot.mindreset.tech"

# ── 屏幕尺寸 ──
SCREEN_W = 296
SCREEN_H = 152

# ── 字体路径（无衬线，笔画粗，墨水屏清晰）──
# macOS 优先冬青黑体，Linux 用 Noto Sans CJK（Dockerfile 安装）
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",       # macOS 冬青黑体（首选）
    "/System/Library/Fonts/STHeiti Medium.ttc",         # macOS 黑体（备选）
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",  # macOS 兜底
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux Noto Sans CJK
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",  # Linux Noto (备选路径)
]

# ── 字号配置 ──
FS_HEADER = 16   # 顶部天气行（℃ 必须够大才能看清圆圈）
FS_POEM = 20     # 诗词正文
FS_SOURCE = 16   # 作者出处
FS_SIG = 14      # 底部签名

# ── 布局参数 ──
HEADER_Y = 3             # 顶部 y 坐标
POEM_Y_START = 36        # 诗词起始 y（距顶部留足呼吸空间）
POEM_LINE_HEIGHT = 26    # 诗词行高（字号20 + 间距6）
SOURCE_GAP = 4           # 出处与诗词的间距
SIG_Y = SCREEN_H - FS_SIG - 4  # 底部 y

# ── 笔画增粗（假粗体：偏移重绘，约1.5倍）
# 在原位基础上向右、向下各偏移1px重绘，竖画横画均匀加粗，
# 但不像 MinFilter 那样全方向膨胀把间隙也填掉导致糊成一片。
BOLD_OFFSETS = [(0, 0), (1, 0), (0, 1)]

# 字体缓存
_font_cache = {}


def _get_font(size):
    """加载指定大小的字体（带缓存）"""
    if size not in _font_cache:
        for path in _FONT_CANDIDATES:
            if os.path.exists(path):
                try:
                    _font_cache[size] = ImageFont.truetype(path, size)
                    break
                except Exception:
                    continue
        else:
            _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


def _draw_bold(draw, xy, text, font, fill=0):
    """绘制文字（带假粗体偏移重绘）"""
    x, y = xy
    for ox, oy in BOLD_OFFSETS:
        draw.text((x + ox, y + oy), text, font=font, fill=fill)


def _draw_centered(draw, text, y, font, fill=0):
    """水平居中绘制一行文字（像素级精确）"""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    # 假粗体向右偏移1px，居中时左移0.5px补偿
    x = (SCREEN_W - text_w - 1) / 2
    _draw_bold(draw, (x, y), text, font, fill=fill)


def _draw_right(draw, text, y, font, fill=0, right_margin=5):
    """右对齐绘制一行文字"""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    # 假粗体向右偏移1px，右对齐时多减1px
    x = SCREEN_W - text_w - right_margin - 1
    _draw_bold(draw, (x, y), text, font, fill=fill)


# ── 二十四节气 ──
# 用 lunar_python（寿星天文历移植）精确计算节气日，只在节气当天显示。
# 此前用 (月,日) 硬编码表覆盖 ±1 天漂移，导致每个节气连续显示 3 天（错）。
def get_solar_term(d=None):
    """返回指定日期（默认今天）的节气名，如果不是节气日则返回 None"""
    if d is None:
        d = date.today()
    jq = _LunarSolar.fromYmd(d.year, d.month, d.day).getLunar().getJieQi()
    return jq or None


# ── 农历日期 ──
_CN_NUMS = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
_LUNAR_MONTHS = ["正月", "二月", "三月", "四月", "五月", "六月",
                 "七月", "八月", "九月", "十月", "冬月", "腊月"]


def _format_lunar_day(day):
    """农历日 → 汉字: 1→初一, 10→初十, 15→十五, 20→二十, 25→廿五, 30→三十"""
    if day == 10:
        return "初十"
    if day == 20:
        return "二十"
    if day == 30:
        return "三十"
    tens = day // 10
    ones = day % 10
    prefix = ["初", "十", "廿"][tens]
    return prefix + _CN_NUMS[ones]


def get_lunar_date_str(d=None):
    """返回农历日期字符串，如 '农历七月初五'"""
    if d is None:
        d = date.today()
    ld = LunarDate.fromSolarDate(d.year, d.month, d.day)
    month_str = ("闰" if ld.isLeapMonth else "") + _LUNAR_MONTHS[ld.month - 1]
    return f"农历{month_str}{_format_lunar_day(ld.day)}"


def generate_image(poem, weather, date_str):
    """生成 296×152 墨水屏图片

    Args:
        poem: 诗词字典（title, author, lines）
        weather: 天气字典（temp_min, temp_max, humidity, description, ultraviolet_desc, aqi, aqi_desc）
        date_str: 日期字符串，如 "8月12日 周二"

    Returns:
        bytes: PNG 图片数据
    """
    img = Image.new("L", (SCREEN_W, SCREEN_H), 255)  # 白底灰度
    draw = ImageDraw.Draw(img)

    f_header = _get_font(FS_HEADER)
    f_poem = _get_font(FS_POEM)
    f_source = _get_font(FS_SOURCE)
    f_sig = _get_font(FS_SIG)

    # ── 顶部：温度区间 + 湿度 + 天气 + 空气质量（左对齐，16px）──
    parts = []
    tmin = weather.get("temp_min")
    tmax = weather.get("temp_max")
    if tmin is not None and tmax is not None:
        parts.append(f"{tmin}~{tmax}℃")
    elif weather.get("temperature") is not None:
        parts.append(f'{weather["temperature"]}℃')
    if weather.get("humidity") is not None:
        parts.append(f"湿度{weather['humidity']}%")
    if weather.get("description"):
        parts.append(weather["description"])
    aqi_desc = weather.get("aqi_desc")
    if aqi_desc:
        parts.append(f"空气{aqi_desc}")
    elif weather.get("aqi") is not None:
        parts.append(f"AQI{weather['aqi']}")
    header_text = " ".join(parts)

    _draw_bold(draw, (5, HEADER_Y), header_text, f_header)

    # ── 中部：诗词（居中，最多2行）+ 出处（居中，16px）──
    poem_lines = poem.get("lines", [])[:2]
    for i, line in enumerate(poem_lines):
        _draw_centered(draw, line, POEM_Y_START + i * POEM_LINE_HEIGHT, f_poem)

    author = poem.get("author", "")
    ptitle = poem.get("title", "无题")
    source = f"——{author}《{ptitle}》" if author else f"——《{ptitle}》"
    source_y = POEM_Y_START + len(poem_lines) * POEM_LINE_HEIGHT + SOURCE_GAP
    _draw_centered(draw, source, source_y, f_source)

    # ── 底部：日期 + 农历 + 节气（右对齐，14px）──
    sig_parts = [date_str.replace(" ", " · ")]  # "8月17日 周一" → "8月17日 · 周一"
    lunar = get_lunar_date_str()
    if lunar:
        sig_parts.append(lunar)
    solar_term = get_solar_term()
    if solar_term:
        sig_parts.append(solar_term)
    _draw_right(draw, " · ".join(sig_parts), SIG_Y, f_sig)

    # 输出 PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def save_preview(poem, weather, date_str, path="/tmp/poetry_preview.png"):
    """生成本地预览图片（调试用）"""
    png = generate_image(poem, weather, date_str)
    with open(path, "wb") as f:
        f.write(png)
    return path


# ── API 调用 ──

def get_loop_list(dot_api_key, device_id):
    """查询设备循环任务列表"""
    url = f"{DOT_API_BASE}/api/authV2/open/device/{device_id}/loop/list"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {dot_api_key}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_image_api_task_key(dot_api_key, device_id):
    """查询设备循环中第一个 IMAGE_API 的 taskKey"""
    try:
        data = get_loop_list(dot_api_key, device_id)
        for item in data:
            if item.get("type") == "IMAGE_API":
                return item.get("key")
    except Exception:
        pass
    return None


def push_to_device(dot_api_key, device_id, poem, weather, date_str):
    """通过 Image API 推送图片到 Dot. 设备

    生成 296×152 图片 → base64 编码 → 推送到 Dot. Image API。

    Args:
        dot_api_key: Dot. API 密钥
        device_id: 设备序列号
        poem: 诗词字典
        weather: 天气字典
        date_str: 日期字符串

    Returns:
        str: API 返回的消息
    """
    png_data = generate_image(poem, weather, date_str)
    b64_image = base64.b64encode(png_data).decode("ascii")

    url = f"{DOT_API_BASE}/api/authV2/open/device/{device_id}/image"
    payload = {
        "refreshNow": True,
        "image": b64_image,
        "border": 0,
        "ditherType": "NONE",
    }

    task_key = get_image_api_task_key(dot_api_key, device_id)
    if task_key:
        payload["taskKey"] = task_key

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
        if e.code in (404, 405):
            if "图像 API" in error_msg:
                raise RuntimeError(
                    "Dot. App 中未启用图像 API 内容槽位。"
                    "请前往 Dot. App → 内容工坊 → 添加「图像 API」到设备循环任务，"
                    "然后重新运行。"
                )
            return _push_via_legacy_api(dot_api_key, device_id, b64_image)
        raise RuntimeError(f"Dot. Image API 错误 {e.code}: {error_msg}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接 Dot. API: {e.reason}")


def _push_via_legacy_api(dot_api_key, device_id, b64_image):
    """回退：使用旧版 /api/open/image endpoint"""
    url = f"{DOT_API_BASE}/api/open/image"
    payload = {
        "refreshNow": True,
        "deviceId": device_id,
        "image": b64_image,
        "link": "https://dot.mindreset.tech",
        "border": 0,
        "ditherType": "NONE",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {dot_api_key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("message", "推送成功(旧API)")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        try:
            error_msg = json.loads(error_body).get("message", error_body)
        except (json.JSONDecodeError, ValueError):
            error_msg = error_body or e.reason
        raise RuntimeError(f"Dot. Image API(旧) 错误 {e.code}: {error_msg}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接 Dot. API: {e.reason}")
