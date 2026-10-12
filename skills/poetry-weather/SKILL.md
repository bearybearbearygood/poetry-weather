---
name: poetry-weather
version: 2.10
description: 诗词天气推送 Skill（Image API 图片直推版，默认主入口）。根据用户所在城市的每日天气自动匹配一首古诗词，用 Pillow 生成 296x152 墨水屏图片推送到 Dot. 设备。当用户说"设置诗词天气推送"、"安装诗词天气"、"Dot. 诗词"、"天气诗词"、"诗词天气"时触发。需要用户提供 Dot. API Key、设备序列号和所在城市。注意：本 skill 是图片版；纯文本推送/Text API/RSS 内容场景请用 poetry-weather-push（文本版）。
agent_created: true
---

# 诗词天气

根据每日天气自动匹配古诗词，生成墨水屏图片推送到 Dot. 设备。晴天有晴诗，雨天有雨诗，高温有夏诗，严寒有冬诗。

> **本 skill 是 Image API 图片直推版**（默认主入口）。另有一个 `poetry-weather-push` 是 Text API 纯文本版（RSS 订阅内容同源）。两者通道不同：图片版效果更好但需要每用户自己的 API Key+序列号，无法公共分发；文本版纯标准库、内容与 RSS 一致。本 skill 与 `poetry-weather-push` 共用同一套天气获取与诗词匹配逻辑（weather.py / poetry.py / poetry.json）。

## 前置条件

用户需要准备以下信息（安装时逐一询问）：

1. **Dot. API Key**（`dot_app_` 开头）— Dot. App → 底部「更多」标签页 → 「API 密钥」→ 「创建 API Key」→ 复制。找不到？确认 App 已更新到最新版（iOS 16+ / Android 12L+）。
2. **Dot. 设备序列号**（12 位字母数字）— Dot. App → 底部「更多」标签页 → 点击头像下方的设备列表 → 选择设备 → 下滑找到「设备序列号」→ 点击复制。
3. **所在城市** — 用于获取天气（也可填经纬度）

> 彩云天气 Token 已内置在 config.example.json 中，无需用户额外申请。

## 安装流程

### 第 1 步：引导用户在 Dot. App 中添加「图像 API」内容槽位

这一步必须先做，否则推送会返回 404。

引导用户操作：
1. 打开 Dot. App
2. 进入设备 → 内容管理 → 循环任务
3. 添加「图像 API」内容到循环任务
4. 保存

### 第 2 步：安装依赖 + 创建配置 + 测试推送

这三件事全部由 AI 自动完成，不需要用户参与。按顺序执行：

**2a. 安装依赖**

```bash
pip install Pillow lunardate lunar_python
```

或按 `scripts/requirements.txt` 安装：

```bash
cd scripts/
pip install -r requirements.txt
```

- `lunar_python`：二十四节气精确计算（寿星天文历移植），只在节气当天显示节气名
- **无需安装中文字体**：skill 自带 500KB 的 Noto Sans CJK 子集字体（OFL 协议），覆盖全部诗词库 + 界面字符，开箱即用。如需更换可用 `POETRY_WEATHER_FONT_PATH` 环境变量覆盖。

**2b. 创建配置文件**

将 `assets/config.example.json` 复制为脚本目录下的 `config.json`，填入用户提供的信息：

```json
{
  "caiyun_token": "75BOLa84lb4SaaYh",
  "location": {
    "lng": 116.4074,
    "lat": 39.9042,
    "name": "北京"
  },
  "dot_api_key": "dot_app_用户提供的密钥",
  "device_id": "用户提供的设备序列号",
  "edition": "general"
}
```

`edition` 字段当前只支持 `general`（137 首通用古诗词库，唐宋为主）。代码层已预留扩展位，未来增加宋词版时只需把 `poetry_ci.json` 放回 scripts/ 目录，在 `poetry.py` 的 `POETRY_PATHS` 加一行 `"ci": POETRY_CI_PATH`，并把 `main.py` 的 `SUPPORTED_EDITIONS` 加上 `"ci"` 即可。非法 edition 值会自动回退到 general 并打印警告。

> 💡 **推荐：把 `config.json` 放在 skill 之外**。技能升级会刷新 skills/ 目录，可能覆盖脚本目录里的 config.json 与 history.json。建议把配置放在固定目录（如 `~/.workbuddy/poetry-weather/`），然后通过环境变量 `POETRY_WEATHER_CONFIG` 指定：
>
> ```bash
> export POETRY_WEATHER_CONFIG=~/.workbuddy/poetry-weather/config.json
> ```
>
> main.py 已支持该环境变量，缺省时仍回退到 scripts/config.json（向后兼容）。

城市经纬度可从 `scripts/cities.json` 中查询。如果用户只提供了城市名，在 cities.json 中查找对应经纬度填入。如果用户不填城市，程序会自动通过 IP 定位。

**2c. 测试推送**

```bash
cd scripts/
/Users/yunzhao/.workbuddy/binaries/python/envs/default/bin/python3 main.py
```

> 注意：必须使用 venv 解释器（已安装 Pillow + lunardate + lunar_python）。managed 3.13.12 解释器缺这些包，直接用会报 ModuleNotFoundError。

如果成功，用户会在 Dot. 设备上看到刷新的诗词图片。如果返回 404，回到第 1 步引导用户添加图像 API 槽位。

### 第 3 步：设置每日自动推送

创建一条定时自动化，每天早上 9:00 运行推送脚本：

- 名称：诗词天气每日推送
- 类型：recurring
- 频率：每天 9:00
- Prompt：运行诗词天气推送脚本，执行 `cd {skill_scripts_dir} && /Users/yunzhao/.workbuddy/binaries/python/envs/default/bin/python3 main.py`
- 需要 WorkBuddy 在定时时刻处于运行状态

用户只需说「每天早上 9 点自动推送诗词天气」，AI 创建自动化即可。

## 文件说明

### scripts/

| 文件 | 作用 |
|------|------|
| `main.py` | 入口，读取配置 → 获取天气 → 匹配诗词 → 生成图片 → 推送 |
| `dot_api.py` | Dot. 设备 API 客户端，用 Pillow 生成 296x152 图片并推送；节气用 lunar_python 精确计算（仅节气日显示） |
| `weather.py` | 彩云天气 API 客户端，获取温度/湿度/AQI/紫外线等 |
| `poetry.py` | 诗词匹配模块，按天气类型选诗；季节为"候选内优先"（非硬过滤），20 天去重窗口 + 窗口自适应 + LRU 兜底 |
| `poetry.json` | 通用古诗词库（229 首，13 类天气，含 22 首高温诗，唐宋为主） |
| `cities.json` | 中国 50 个主要城市经纬度 |
| `requirements.txt` | Python 依赖 |
| `add_poems.py` | 诗库追加工具（带校验：2 行、每行 5~9 字、季节合法、类别内不重复） |
| `subset_font.py` | 子集字体生成脚本（**新增诗词后必须重跑**，否则新字缺字） |

### fonts/

| 文件 | 作用 |
|------|------|
| `poetry-weather.ttf` | 内置子集中文字体（OFL 协议），从 Noto Sans CJK SC 子集化，覆盖全部诗词库 + UI 字符，约 600KB，开箱即用 |

### assets/

| 文件 | 作用 |
|------|------|
| `config.example.json` | 配置模板，彩云 Token 已内置，复制为 config.json 后填 Dot. 密钥和城市 |

## 墨水屏排版

296x152px 图片布局：

```
┌─────────────────────────────────┐
│ 24~26℃ 湿度95% 阴 空气优        │ ← 顶部 16px 左对齐（温度+湿度+天气+空气质量）
│                                 │
│       永日不可暮，              │ ← 诗词 20px 居中
│       炎蒸毒我肠。              │ ← 诗词 20px 居中
│      ——杜甫《夏夜叹》           │ ← 出处 16px 居中
│                                 │
│  8月17日 · 周一 · 农历七月初五   │ ← 底部 14px 右对齐（日期+农历+节气）
└─────────────────────────────────┘
```

- 顶部：温度区间 + 湿度 + 天气描述 + 空气质量（不再显示紫外线和节气）
- 底部：日期 + 农历 + 节气（仅节气日显示节气名；节气用 lunar_python 精确计算，自动处理年份漂移，2026-08-24 起生效）
- 紫外线已于 2026-08-17 移除（9点实时值失真，参考价值低）

- 字体：自带 Noto Sans CJK SC 子集字体（poetry-weather.ttf，OFL 协议），无衬线，墨水屏清晰
- 假粗体：水平/垂直偏移重绘，笔画增粗约 1.5 倍，墨水屏竖画清晰不糊
- 像素级居中：textbbox 测量文字宽度后计算 x 坐标

## 触发与匹配逻辑

1. **触发条件**：
   - 彩云 skycon → 天气类型（晴/多云/阴/雨/雪…）。v2.5 起取「**实时 + 当天预报（daily.skycon / skycon_08h_20h）三者中严重度最高者**」，避免雷阵雨来临前推送时刻恰好是晴而误推晴天诗
   - 温度≥32℃ 或 舒适度指数≤2 追加「高温」
   - 温度≤5℃ 或 舒适度指数≥7 追加「严寒」
   - 湿度 ≥92% 且 skycon 不是晴/多云/阴/雨/雪 → 追加「雾」（2026-08-21 收紧：阈值从 85 提到 92，避免南方潮湿天误推雾诗）
2. **优先级**：hot/cold > 大雨/大雪 > 沙尘/霾/雾/大风 > 雨/雪 > 阴 > 多云 > 晴（极端天气优先）
3. **季节优先**：先排除 20 天去重窗口内推送过的诗，**候选内**再优先当前季节（含 all）。季节是"偏好"不是"硬过滤"——硬过滤会让当季小池（秋季 clear 只有 4 首）几天就刷完窗口，反而形成短周期轮转
4. **去重**：最近 20 天推送过的诗不重复（按 `edition` 分别记录与匹配）；若整池被窗口占满（池子比窗口小），窗口自动收窄到「池子大小 − 1」，保证池内始终有候选，轮转周期等于池子大小；最后才用 LRU 兜底

> 2026-09-22 修复（v2.10）：此前季节用硬过滤，秋季 `clear` 候选只剩 4 首、`rain` 只剩 3 首，4 天刷完 20 天窗口后 LRU 接管，形成固定的 4 天循环（9/10~9/22 推送记录完全吻合）。改为"候选内优先 + 窗口自适应"后，秋季 clear 候选 4 → 26 首，最短重复间隔 4 天 → 20 天。诗库同步从 137 条扩到 243 条（唯一 229 首）。
>
> 2026-08-17 调整：舒适度触发高温的阈值从 ≤3 收紧到 ≤2（仅闷热/酷热/炎热触发，体感"热"不再霸屏高温诗），高温诗池同步扩充到 22 首。

## 常见问题

**推送返回 404**：Dot. App 中未添加「图像 API」内容槽位。引导用户在 Dot. App → 循环任务中添加。

**获取天气失败**：config.example.json 中已内置彩云天气 Token，正常不会出错。如遇到限流，可在 https://dashboard.caiyunapp.com/ 免费注册自己的 Token 替换。

**显示成几条粗黑杠（已修复）**：v2.4 及更早版本上，少数设备（如 Linux/Windows 或缺少中文字体的 macOS）会因系统无中文字体而把缺字占位符糊成黑条。v2.5 起内置 Noto Sans CJK 子集字体，开箱即用。

**诗句重复出现**：先查候选池是否小于 20 天去重窗口。跑 `python3 -c "from poetry import load_poetry; db=load_poetry(); [print(k, len(v)) for k,v in db.items()]"` 看各类池子大小；池子 < 20 首的类别轮转周期就等于池子大小。补诗用 `add_poems.py`，**补完必须重跑 `subset_font.py`**，否则新字会缺字。详见 `references/maintenance.md`。

**IP 定位不准**：在 config.json 中填写 location.lng 和 location.lat 手动指定
