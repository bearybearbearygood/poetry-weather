"""Dot. 墨水屏设备 API 客户端 — Image API 版

用 Pillow 生成 296×152 图片，像素级控制排版：
- 诗词真正居中（textbbox 测量宽度后计算 x 坐标，五言七言都能对齐）
- 无衬线字体（冬青黑体）+ 假粗体（水平/垂直偏移重绘，增粗约1.5倍），墨水屏竖画清晰且不糊
- 每行独立字号：诗 20px、出处 16px、签名 14px、顶部 16px
- 底部右对齐
- 节气当天在顶部天气行末尾显示
- base64 PNG 推送到 Dot. Image API

布局效果（296×152px）：
┌─────────────────────────────────┐
│ 24~26℃ 湿度95% 阴  立秋        │ ← 顶部 14px 左对齐 + 节气
│                                 │
│       永日不可暮，              │ ← 诗词 20px 居中
│       炎蒸毒我肠。              │ ← 诗词 20px 居中
│      ——杜甫《夏夜叹》           │ ← 出处 16px 居中
│                                 │
│        紫外线很弱 · 空气优 · 8月12日 │ ← 底部 14px 右对齐
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

DOT_API_BASE = "https://dot.mindreset.tech"

# ── 屏幕尺寸 ──
SCREEN_W = 296
SCREEN_H = 152

# ── 字体路径（无衬线，笔画粗，墨水屏清晰）──
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",       # 冬青黑体（首选，笔画粗圆）
    "/System/Library/Fonts/STHeiti Medium.ttc",         # 黑体（备选）
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",  # Arial Unicode（兜底）
]

# ── 字号配置 ──
FS_HEADER = 16   # 顶部天气行（℃ 必须够大才能看清圆圈）
FS_POEM = 20     # 诗词正文
FS_SOURCE = 16   # 作者出处
FS_SIG = 14      # 底部签名

# ── 布局参数 ──
HEADER_Y = 3             # 顶部 y 坐标
POEM_Y_START = 30        # 诗词起始 y
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
# 覆盖每年可能出现的日期（±1~2天波动），用 (month, day) → 节气名 查表
_SOLAR_TERMS = {
    (1, 5): "小寒", (1, 6): "小寒",
    (1, 20): "大寒", (1, 21): "大寒",
    (2, 3): "立春", (2, 4): "立春", (2, 5): "立春",
    (2, 18): "雨水", (2, 19): "雨水",
    (3, 5): "惊蛰", (3, 6): "惊蛰",
    (3, 20): "春分", (3, 21): "春分",
    (4, 4): "清明", (4, 5): "清明",
    (4, 19): "谷雨", (4, 20): "谷雨",
    (5, 5): "立夏", (5, 6): "立夏",
    (5, 20): "小满", (5, 21): "小满",
    (6, 5): "芒种", (6, 6): "芒种",
    (6, 21): "夏至", (6, 22): "夏至",
    (7, 7): "小暑", (7, 8): "小暑",
    (7, 22): "大暑", (7, 23): "大暑",
    (8, 7): "立秋", (8, 8): "立秋",
    (8, 23): "处暑", (8, 24): "处暑",
    (9, 7): "白露", (9, 8): "白露",
    (9, 22): "秋分", (9, 23): "秋分",
    (10, 8): "寒露", (10, 9): "寒露",
    (10, 23): "霜降", (10, 24): "霜降",
    (11, 7): "立冬", (11, 8): "立冬",
    (11, 22): "小雪", (11, 23): "小雪",
    (12, 7): "大雪", (12, 8): "大雪",
    (12, 21): "冬至", (12, 22): "冬至",
}


def get_solar_term():
    """返回今天的节气名，如果不是节气日则返回 None"""
    today = date.today()
    return _SOLAR_TERMS.get((today.month, today.day))


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

    # ── 顶部：温度区间 + 湿度 + 天气 + 节气（左对齐，14px）──
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
    header_text = " ".join(parts)

    # 如果今天是节气日，追加节气名（间隔两个空格）
    solar_term = get_solar_term()
    if solar_term:
        header_text += "  " + solar_term

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

    # ── 底部：紫外线 + AQI + 日期（右对齐，14px）──
    sig_parts = []
    if weather.get("ultraviolet_desc"):
        sig_parts.append(f"紫外线{weather['ultraviolet_desc']}")
    aqi = weather.get("aqi")
    aqi_desc = weather.get("aqi_desc")
    if aqi is not None and aqi_desc:
        sig_parts.append(f"空气{aqi_desc}")
    elif aqi is not None:
        sig_parts.append(f"AQI{aqi}")
    sig_parts.append(date_str)
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
