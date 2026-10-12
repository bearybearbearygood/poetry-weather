# 维护手册：去重排查与诗库扩充

## 一、症状 → 排查路径

用户反馈"诗句重复了""同一首诗又来了"，按下面顺序查：

### 1. 看候选池大小

选诗范围由「天气类别池」决定。池子小于去重窗口（20 天）时，轮转周期就等于池子大小——这是唯一可能的重复来源。

```bash
cd <skill>/scripts
python3 -c "
from poetry import load_poetry
db = load_poetry()
for k, v in db.items():
    print(f'{k:<16} {len(v):>3} 首  →  轮转周期 {min(len(v),20)} 天')
"
```

池子 ≥ 21 首的类别：最短重复间隔 = 20 天（去重窗口生效）。
池子 < 20 首的类别：最短重复间隔 = 池子大小，属预期行为，只能靠补诗解决。

### 2. 看推送历史

```bash
python3 -c "
import json
h = json.load(open('history.json'))
for it in h['sent'][-14:]:
    print(it['timestamp'][:10], it['weather'], it['title'])
"
```

如果出现 A→B→C→D→A→B→C→D 这种等间隔循环，就是池子被刷完了。

### 3. 复现验证

用 `poetry.select_poem` 直接模拟，注意 `days_since` 是拿 `datetime.now()` 比的——**模拟时必须把已推送诗的时间戳换算成"距当前模拟日多少天前"**，否则全都会判为可推，模拟结果无效（这是踩过的坑）。

```python
import random
from datetime import datetime, timedelta
from poetry import load_poetry, select_poem, poem_key

db, NOW = load_poetry(), datetime.now()
rng, pushed, gaps = random.Random(42), {}, []
for d in range(1, 81):
    last = {k: (NOW - timedelta(days=d - pd)).isoformat() for k, pd in pushed.items()}
    p, _ = select_poem(db, ['clear'], last, 20, rng=rng)
    k = poem_key(p)
    if k in pushed:
        gaps.append(d - pushed[k])
    pushed[k] = d
print('最短重复间隔:', min(gaps))
```

## 二、扩充诗库

### 硬约束（墨水屏渲染决定，不可放宽）

| 约束 | 值 | 原因 |
|------|-----|------|
| 行数 | **恰好 2 行** | `dot_api.py` 只取 `lines[:2]` |
| 每行字符数 | **5~9**（含标点） | 屏宽 296px、字号 20px，超过 9 字顶破屏幕 |
| season 取值 | spring / summer / autumn / winter / all | `get_season()` 返回这四种 + all 兜底 |
| 类别内唯一 | title\|author 不可重复 | 去重表按 `title\|author` 做键 |

### 操作

```bash
cd <skill>/scripts
# 1. 写 additions.json（顶层 key 为天气类别）
# 2. 先校验，不写入
python3 add_poems.py additions.json --dry-run
# 3. 校验通过再写入
python3 add_poems.py additions.json
# 4. 必须重跑子集字体，否则新字在墨水屏上是空白
python3 subset_font.py
```

### 重跑字体后验证覆盖率

```bash
python3 -c "
from fontTools.ttLib import TTFont
from poetry import load_poetry
cmap = set()
for t in TTFont('fonts/poetry-weather.ttf')['cmap'].tables:
    cmap.update(t.cmap.keys())
need = set()
for v in load_poetry().values():
    for p in v:
        need.update(p['title'] + p['author'] + p['dynasty'])
        need.update(''.join(p['lines']))
missing = sorted(c for c in need if c.strip() and ord(c) not in cmap)
print('缺字:', missing or '无')
"
```

## 三、一个坑：同名不同内容的诗

去重键是 `title|author`。有两种情况会被当成同一首：

- **同一首诗的不同摘句**（如柳宗元《江雪》在 `cloudy` 用「千山鸟飞绝」、在 `snow` 用「孤舟蓑笠翁」）—— 这是**期望行为**，同一首诗不应因天气类别不同而重复出现。
- **同名但确实不同的诗**（如杜甫三首《绝句》）—— 这是**键冲突**，会白占候选位，且 LRU 兜底时可能把"另一首"推出来，看起来像重复。

排查：

```bash
python3 -c "
import json
from collections import defaultdict
g = defaultdict(set)
for cat, v in json.load(open('poetry.json')).items():
    for p in v:
        g[f\"{p['title']}|{p['author']}\"].add(p['lines'][0])
for k, firsts in g.items():
    if len(firsts) > 1:
        print(k, '→', sorted(firsts))
"
```

如果某个键下的首句差异代表的是**不同首诗**，给它们的 title 加上区分后缀（如《绝句·迟日江山丽》）；如果只是**同一首的不同摘句**，保持原样不动。

## 四、发布流程（改完代码 → 让朋友用上）

改动落在主项目 `/Users/yunzhao/WorkBuddy/诗词天气`（`poetry-weather` 是它的符号链接，同一目录）。

### 1. 提交并推送

备份文件（`*.bak-*`）已在 `.gitignore` 忽略，不会被误提交。

```bash
cd /Users/yunzhao/WorkBuddy/诗词天气
git add <改动文件>
git commit
git tag -a v2.x -m "..."
```

**推送必须走本机代理**：沙箱自带的代理会拒绝 GitHub 的 CONNECT 隧道（502），直连 `api.github.com` 超时。唯一通路是本机代理软件的端口（默认 7897，代理软件重启后端口可能变，失效时先探测 7890/7891/1087/8888/1080）。

必须**同时设大小写两套**变量，只设大写会被沙箱代理截走；且需 disable sandbox：

```bash
HTTPS_PROXY=http://127.0.0.1:7897 https_proxy=http://127.0.0.1:7897 \
HTTP_PROXY=http://127.0.0.1:7897 http_proxy=http://127.0.0.1:7897 \
git push origin main
git push origin v2.x
```

推送后核对：`git rev-list --left-right --count origin/main...main` 应为 `0 0`；远端 tag 用
`git ls-remote --tags origin`（同样要带代理）确认。

### 2. Render 手动部署（关键，容易漏）

Render **不会自动部署**——repo 的 webhooks 列表为空，没有自动触发源。推完 GitHub 必须去
Render Dashboard → 目标服务 → Manual Deploy 手动触发，否则托管服务跑的还是旧代码，朋友们收不到修复。

`server.py` 没有暴露版本端点，所以**无法远程探测 Render 上跑的是哪个 commit**，只能靠这次手动部署动作来保证。

## 五、改页面后怎么本地验证（别用 Chrome 无头）

改 `templates/` 或 `static/style.css` 之后，必须真实渲染再看，不要凭 CSS 代码推断。**Chrome 的 `--headless` 在这台机器上不可用**：GPU 进程会 `exit_code=6` 崩溃、`--dump-dom` 输出为空、`--screenshot` 时灵时不灵；更坑的是 `--window-size` 设定的视口不准，截出的图看着像"内容贴边/被裁"，实际是假象（曾在首页改版时据此误判出一次不存在的"移动端横向溢出"）。

**正确做法：playwright + 复用已缓存的 chromium。**

```bash
# 装包（一次即可）
/Users/yunzhao/.workbuddy/binaries/python/envs/default/bin/pip install playwright
```

```python
from playwright.sync_api import sync_playwright

EXEC = ("/Users/yunzhao/Library/Caches/ms-playwright/"
        "chromium_headless_shell-1223/chrome-headless-shell-mac-arm64/chrome-headless-shell")
# playwright 1.63 默认找 chromium_headless_shell-1243，缓存里只有 1223 → 必须显式指定

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXEC, args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    pg.goto("http://127.0.0.1:8095/", wait_until="load")
    m = pg.evaluate("""() => ({
        innerWidth: window.innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        btnWidths: [...document.querySelectorAll('.cta-actions .btn')]
                     .map(e => Math.round(e.getBoundingClientRect().width)),
        overflow: [...document.querySelectorAll('body *')]
            .filter(e => e.getBoundingClientRect().right > window.innerWidth + 0.5)
            .map(e => e.tagName + '.' + e.className).slice(0, 8)
    })""")
    print(m)                              # 判定布局问题只认这些数字
    pg.screenshot(path="preview.png", full_page=True)
    b.close()
```

**判据**：`scrollWidth == innerWidth` 且 `overflow` 为空 = 没有横向溢出。

**临时预览服务**：另起一个只渲染模板的 Flask 实例，**不要直接跑 `server.py`**（它会连 SQLite 订阅库并启动调度器，有误推真实设备的风险）：

```python
app = Flask(__name__, template_folder=f"{ROOT}/templates", static_folder=f"{ROOT}/static")
@app.route("/")
def index(): return render_template("push_index.html")
# 模板里用到的 url_for 端点（register / guide / index）都得注册，否则渲染报错
```

验证完记得 `lsof -ti:<port> | xargs kill` 停掉服务。

**改样式前先查类是不是跨页共享**：`style.css` 里的 `.hero` / `.cta` / `.feature-card` 被 `push_index.html`、`guide.html`、`index.html`（RSS 首页，由 `rss_server.py` 渲染）共用，改一处会同时影响几个页面，改完要逐个页面确认。`templates/index.html` 不是死文件——它服务于 RSS 通道。
