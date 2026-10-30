# 诗词天气 · 内容工坊接口

给 Dot. 内容工坊单独做的一套服务，**与主项目的 RSS / 推送功能完全隔离**。

主项目里的 `rss_server.py`、`main.py`、`server.py`、`weather.py` 一行都没改，
个人自用和已分发的 skill 不受影响。

## 这个目录做什么

只提供一个只读接口：

```
GET /api/daily?city=杭州
```

返回当日天气 + 匹配的诗句，供内容工坊渲染成一张卡片。

## 为什么单独做一套

内容工坊接入需要的是「用户填城市 → 返回内容」这种按需查询，
和个人用的「每天固定推一张图到自己的设备」是两种完全不同的用法：

| | 主项目 | 本目录 |
|---|---|---|
| 触发方式 | 定时推送 / RSS 拉取 | HTTPS 请求 |
| 城市 | 本地配置写死 | 用户填 |
| 输出 | 图片 / RSS XML | JSON |
| 依赖 | config.json、设备密钥 | 只需环境变量 |

混在一起改会牵连到已经在用的 skill，所以分开放。

## 运行

```bash
pip install -r requirements.txt
CAIYUN_TOKEN=你的彩云token python3 app.py
```

默认监听 8100 端口。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `WEATHER_PROVIDER` | `qweather` | `qweather` / `caiyun` / `open-meteo` |
| `QWEATHER_HOST` | 空 | 账号专属 API Host，形如 `xxxxx.re.qweatherapi.com` |
| `QWEATHER_KID` | 空 | 凭据 ID（JWT 的 `kid`） |
| `QWEATHER_SUB` | 空 | 项目 ID（JWT 的 `sub`） |
| `QWEATHER_ISS` | 空 | 开发者 ID，Q 开头（JWT 的 `iss`） |
| `QWEATHER_PRIVATE_KEY` | 空 | Ed25519 私钥的 PEM 全文，不设则读 `secrets/ed25519-private.pem` |
| `CAIYUN_TOKEN` | 空 | 彩云 token，`provider=caiyun` 时必填 |
| `DEFAULT_CITY` | `北京` | 未传 `city` 参数时使用 |
| `PORT` | `8100` | 监听端口 |

## 接口

### `GET /api/daily?city=<城市名>`

`city` 可省略，省略时用默认城市。

成功返回 200：

```json
{
  "ok": true,
  "city": "北京",
  "date": "2026-10-30",
  "date_text": "10月30日 周五",
  "weather": {
    "text": "晴", "temperature": 15,
    "temp_min": 7, "temp_max": 21,
    "humidity": 17, "wind_speed": 2.4,
    "comfort": "舒适", "aqi": "良"
  },
  "poem": {
    "title": "秋夕", "author": "杜牧", "dynasty": "唐",
    "lines": ["银烛秋光冷画屏，", "轻罗小扇扑流萤。"]
  },
  "display": {
    "title": "7~21℃ 晴 舒适",
    "lines": ["银烛秋光冷画屏，", "轻罗小扇扑流萤。"],
    "source": "——杜牧（唐）《秋夕》"
  },
  "cache_ttl": 1800
}
```

`display` 是给渲染方直接用的三段文本，`weather` / `poem` 是原始结构，任选其一。

城市解析失败返回 400：

```json
{"ok": false, "error": "city_not_found", "message": "无法解析这个城市：xxx"}
```

天气源故障返回 503，不会用空内容冒充成功。

### `GET /health`

存活检查，返回当前数据源与城市表条目数。

## 城市解析

`cities_cn.json` 是内置的全国地名表，24,440 条，762 KB，源自 GeoNames（CC-BY-4.0）。

优先级：内置表 → Open-Meteo Geocoding 兜底。正常情况不会走网络。

区县级不做模糊降级：输入「朝阳区」能命中北京朝阳区；解析不了就返回 400 让用户重填，
不会拿一个同名小镇的天气糊弄过去。

重新生成（数据过期时）：

```bash
curl -O https://download.geonames.org/export/dump/CN.zip
unzip CN.zip
python3 ../scripts/build_city_table.py CN.txt
```

## 天气源为什么默认和风

Dot 内容工坊里的官方天气内容（`qweather.weather_now`、`weather_now_and_forecast` 等六个）
用的就是和风天气。我们同样走和风，是为了**数据一致**：

同一个城市、同一时刻，如果诗词卡片显示「晴 21℃」而官方天气卡片显示「多云 18℃」，
用户第一反应是这个东西不可信——诗写得再好也没用。

实测对比（北京，同一时刻）：

| | 和风 | 彩云 | Open-Meteo |
|---|---|---|---|
| 温度 | 21.2℃ | 21.5℃ | 20℃ |
| 湿度 | **15%** | 17% | **53%** |
| AQI | 67 良 | 良 | 62（另次 124） |

和风与彩云在国内数据上高度一致；Open-Meteo 靠全球模型推算，湿度差了 3 倍。

彩云保留为备选源（`WEATHER_PROVIDER=caiyun`），它的问题不是精度而是**限流**：
免费 token 连续请求 3 次就返回 429，公开服务容易撞上。

### 和风接入的两个坑

1. **必须用账号专属 API Host**。公共域名 `devapi.qweather.com` 现在返回 `Invalid Host`，
   要换成控制台分配的 `xxxxx.re.qweatherapi.com`。
2. **返回体是 gzip**。不解压会拿到乱码，客户端里已统一处理。

### 鉴权方式：JWT（Ed25519）

不是简单的 `?key=xxx`。需要：

1. 本地生成 Ed25519 密钥对
   ```bash
   openssl genpkey -algorithm ED25519 -out ed25519-private.pem
   openssl pkey -pubout -in ed25519-private.pem > ed25519-public.pem
   ```
2. 把**公钥**上传到控制台 → 项目管理 → 添加凭据 → 身份认证方式选 JSON Web Token
3. 保存后得到**凭据 ID**（JWT 的 `kid`）
4. 签名时用本地留着的**私钥**

JWT 三个标识缺一不可：`kid` 凭据 ID、`sub` 项目 ID、`iss` 开发者 ID（控制台-设置里那个 Q 开头的）。

私钥放进 `secrets/` 且已在 `.gitignore` 里排除。部署到云主机时用 `QWEATHER_PRIVATE_KEY`
环境变量传整段 PEM，不要让私钥跟仓库走。

## 维护注意

`weather.py` 是从主项目快照过来的副本（加了多源分发）。

主项目如果改了天气字段或解析逻辑，这里**不会自动同步**，需要手动对齐。
这么做是为了让本目录能独立部署——只拷这一个目录就能跑起来。

诗库不复制，直接读主项目的 `poetry.json`，避免补诗后两处不一致。
