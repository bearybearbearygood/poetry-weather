# 诗词天气 v2.5

根据每日天气自动匹配古诗词，推送到 Dot. 墨水屏设备。

晴天有晴诗，雨天有雨诗，高温有夏诗，严寒有冬诗。每天在墨水屏上静静呈现一首应景的古诗词，搭配当日天气信息。

## v2.5 更新

- **内置中文字体**：自带 500KB 的 Noto Sans CJK SC 子集字体（OFL 协议），覆盖全部诗词库 + 界面字符，**无需在系统安装中文字体**，开箱即用。
- **天气判断更准**：取「实时 + 当天预报（全天综合 + 白天）三者中严重度最高者」，避免雷阵雨来临前推送时刻恰好是晴而误推晴天诗。
- **字体查找更稳健**：找不到可用中文字体时直接报错并提示，而不是静默回退到默认字体把中文糊成黑条。

## 效果展示

```
┌─────────────────────────────────┐
│ 24~26℃ 湿度95% 阴  立秋        │ ← 顶部 16px 左对齐 + 节气
│                                 │
│       永日不可暮，              │ ← 诗词 20px 居中
│       炎蒸毒我肠。              │ ← 诗词 20px 居中
│      ——杜甫《夏夜叹》           │ ← 出处 16px 居中
│                                 │
│   紫外线很弱 · 空气优 · 8月12日 │ ← 底部 14px 右对齐
└─────────────────────────────────┘
       296×152px 墨水屏
```

## 工作原理

```
彩云天气 API → 获取实时天气 → 匹配古诗词 → 生成图片/RSS
                    ↓                              ↓
            Dot. Image API 直推            Dot. 设备定时拉取 RSS
            （单用户，main.py）           （多用户，rss_server.py）
```

## 快速部署

### 方式一：命令行直推（单用户，推荐个人使用）

通过 Dot. Image API 生成图片直接推送到设备，像素级控制排版。

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置
cp config.example.json config.json
# 编辑 config.json，填入彩云天气 Token、Dot. API 密钥和设备序列号

# 3. 运行
python main.py

# 4.（可选）配合定时任务实现每日自动推送
crontab -e
# 每天早上 7:00 推送
0 7 * * * cd /path/to/诗词天气 && python3 main.py >> push.log 2>&1
```

> **注意**：Image API 模式需要在 Dot. App 中为设备添加「图像 API」内容槽位到循环任务。

### 方式二：RSS 服务（多用户）

部署 Web 服务，用户在 Dot. App 中添加 RSS 链接即可订阅。

```bash
# Docker 部署（推荐）
cp .env.example .env
# 编辑 .env 填入 CAIYUN_TOKEN
docker-compose up -d
# 访问 http://你的服务器IP:8080

# 或直接运行
pip install -r requirements.txt
export CAIYUN_TOKEN=你的彩云天气Token
python rss_server.py
```

RSS 链接格式：
- `http://域名/rss` — 默认北京
- `http://域名/rss?city=上海` — 指定城市
- `http://域名/rss?lng=121.47&lat=31.23` — 自定义经纬度
- `http://域名/rss?edition=ci` — 宋词版（默认 general 通用古诗词）

## 配置说明

### config.json（单用户模式）

| 字段 | 说明 | 示例 |
|------|------|------|
| `caiyun_token` | 彩云天气 API Token | `你的彩云Token` |
| `location.lng` | 经度 | `116.4074` |
| `location.lat` | 纬度 | `39.9042` |
| `location.name` | 位置名称 | `北京` |
| `dot_api_key` | Dot. API 密钥 | `dot_app_xxx` |
| `device_id` | 设备序列号 | `ABCD1234ABCD` |

### 环境变量（RSS 服务）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CAIYUN_TOKEN` | 彩云天气 Token | 从 config.json 读取 |
| `PORT` | Web 服务端口 | `8080` |
| `FLASK_SECRET_KEY` | Flask 密钥 | 内置默认值 |

## 项目结构

```
诗词天气/
├── main.py              # 单用户入口（Image API 直推）
├── rss_server.py        # RSS Feed 服务（Flask，多用户）
├── weather.py           # 彩云天气 API 客户端
├── dot_api.py           # Dot. 设备 Image API 客户端（Pillow 生成图片）
├── poetry.py            # 诗词匹配模块
├── poetry.json          # 通用诗词库（123 首，13 类天气）
├── poetry_ci.json       # 宋词库（37 首，13 类天气）
├── cities.json          # 中国 50 个主要城市经纬度
├── templates/           # Web 页面
├── static/              # 样式表
├── Dockerfile           # Docker 镜像构建
├── docker-compose.yml   # Docker Compose 部署
├── requirements.txt     # Python 依赖
├── config.example.json  # 单用户配置模板
└── .env.example         # 环境变量模板
```

## 技术细节

- **天气数据**：彩云天气 API v2.6，获取实时温度、湿度、AQI、紫外线、舒适度
- **图片生成**：Pillow 生成 296×152 灰度 PNG，`textbbox` 测量文字宽度实现像素级居中
- **假粗体**：内置 Noto Sans CJK SC 子集字体 + 水平/垂直偏移重绘，笔画增粗约 1.5 倍
- **节气显示**：24 节气查表，当天是节气日时在顶部显示
- **天气类型**：v2.5 起取「实时 + 当天预报」三者中严重度最高者
- **诗词匹配**：13 种天气/温度类型触发，季节优先，每日种子去重
- **多版本文库**：`edition` 参数切换不同诗词 JSON，匹配引擎与触发逻辑完全复用
- **RSS 缓存**：同一天同一城市只请求一次天气 API

### 诗词匹配优先级

```
高温/严寒 > 大雨/大雪 > 沙尘/雾霾/雾/大风 > 雨/雪 > 阴 > 多云 > 晴
```

## 依赖

- Python 3.10+
- `flask`（RSS 服务）
- `Pillow`（Image API 图片生成，**v2.5 起内置中文字体，不再依赖系统字体**）

## License

MIT
