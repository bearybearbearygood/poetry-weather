# 诗词天气

根据每日天气自动匹配古诗词，通过 RSS 订阅推送到 Dot. 墨水屏设备。

晴天有晴诗，雨天有雨诗，高温有夏诗，严寒有冬诗。每天在墨水屏上静静呈现一首应景的古诗词，搭配当日天气信息。

## 效果展示

```
┌─────────────────────────────────┐
│  30℃ 多云 闷热                    │
│                                 │
│  永日不可暮，                      │
│  炎蒸毒我肠。                      │
│  ——杜甫《夏夜叹》                 │
│                                 │
│  湿度77% · 风速3m/s · 空气优       │
│  · 8月4日 周二                    │
└─────────────────────────────────┘
       296×152px 墨水屏
```

## 工作原理

```
彩云天气 API → 获取实时天气 → 匹配古诗词 → 生成 RSS Feed
                                              ↓
                              Dot. 设备定时拉取 RSS ← 用户在 App 中添加订阅
```

用户无需注册、无需提供 API 密钥，只需在 Dot. App 中添加一个 RSS 链接。

## 快速部署

### Docker 部署（推荐）

```bash
# 1. 复制环境变量配置
cp .env.example .env

# 2. 启动服务
docker-compose up -d

# 3. 访问
# http://你的服务器IP:8080
```

### 直接运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置（二选一）
#    a) 环境变量
export CAIYUN_TOKEN=你的彩云天气Token
#    b) 或编辑 config.json

# 3. 启动
python rss_server.py
```

## 用户使用方式

### RSS 订阅（多用户）

1. 访问服务首页 `http://你的服务器IP:8080`
2. 选择城市，复制 RSS 链接（如 `http://你的域名/rss?city=北京`）
3. 打开 Dot. App → 内容工坊 → RSS 订阅
4. 粘贴 RSS 链接，添加到设备循环任务
5. 完成！设备每天自动展示新内容

RSS 链接格式：
- `http://域名/rss` — 默认北京
- `http://域名/rss?city=上海` — 指定城市
- `http://域名/rss?lng=121.47&lat=31.23` — 自定义经纬度

### 命令行直推（单用户）

适合个人使用，通过 Dot. Text API 直接推送到设备：

```bash
# 1. 配置
cp config.example.json config.json
# 编辑 config.json，填入 Dot. API 密钥和设备序列号

# 2. 运行
python main.py
```

配合 crontab 实现每日自动推送：

```bash
# 每天早上 7:00 推送
0 7 * * * cd /path/to/诗词天气 && python3 main.py >> push.log 2>&1
```

## 配置说明

### 环境变量（RSS 服务）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CAIYUN_TOKEN` | 彩云天气 Token | 从 config.json 读取 |
| `PORT` | Web 服务端口 | `8080` |
| `FLASK_SECRET_KEY` | Flask 密钥 | 内置默认值 |

### config.json（单用户模式）

| 字段 | 说明 | 示例 |
|------|------|------|
| `caiyun_token` | 彩云天气 API Token | `你的彩云Token` |
| `location.lng` | 经度 | `116.4074` |
| `location.lat` | 纬度 | `39.9042` |
| `location.name` | 位置名称 | `北京` |
| `dot_api_key` | Dot. API 密钥 | `dot_app_xxx` |
| `device_id` | 设备序列号 | `ABCD1234ABCD` |

## 项目结构

```
诗词天气/
├── rss_server.py        # RSS Feed 服务（Flask）
├── main.py              # 单用户命令行入口（Text API 直推）
├── weather.py           # 彩云天气 API 客户端
├── dot_api.py           # Dot. 设备 Text API 客户端
├── poetry.py            # 诗词匹配模块
├── poetry.json          # 诗词数据库（123 首，13 类天气）
├── cities.json          # 中国 50 个主要城市经纬度
├── templates/
│   ├── base.html        # 基础布局
│   └── index.html       # 首页（RSS 订阅说明）
├── static/
│   └── style.css        # 样式表
├── Dockerfile           # Docker 镜像构建
├── docker-compose.yml   # Docker Compose 部署
├── requirements.txt     # Python 依赖（仅 flask）
├── config.example.json  # 单用户配置模板
├── .env.example         # 环境变量模板
└── .gitignore
```

## 技术细节

- **天气数据**：彩云天气 API v2.6，获取实时温度、湿度、风速、AQI、舒适度
- **诗词匹配**：13 种天气/温度类型触发，季节优先，每日种子去重
- **RSS 缓存**：同一天同一城市只请求一次天气 API，返回相同内容
- **随机种子**：使用日期+坐标作为种子，保证同一天同一位置选到同一首诗

### 诗词匹配优先级

```
高温/严寒 > 大雨/大雪 > 沙尘/雾霾/雾/大风 > 雨/雪 > 阴 > 多云 > 晴
```

## 入驻 Dot. 内容工坊

如果希望成为 Dot. 官方内容源：

1. **部署服务**：确保稳定运行，有公网可访问的域名
2. **联系 Dot. 团队**：
   - GitHub：https://github.com/MindReset/dot_skill/issues
   - 通过 Dot. App 内反馈渠道
3. **提交提案**：说明内容源价值（天气+诗词的独特组合）、技术实现、RSS 地址

## 依赖

- Python 3.10+
- RSS 服务：flask
- 单用户模式：仅 Python 标准库

## License

MIT
