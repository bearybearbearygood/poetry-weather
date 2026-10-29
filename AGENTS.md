# AGENTS.md

本仓库同时是一个 **agent skill 仓库**。用户在对话里说「帮我安装这个 skill：<某个地址>」时，按下面的步骤操作。

## 第 1 步：拿到 skill 目录

两种入口，**优先用 A**：

### 方式 A —— 下载发布包（推荐，国内网络可用）

```bash
curl -fL --max-time 120 -o /tmp/pw-skill.zip https://poetry-weather.onrender.com/download/poetry-weather-skill.zip
unzip -oq /tmp/pw-skill.zip -d /tmp/pw-skill
```

解压后 skill 目录在 `/tmp/pw-skill/poetry-weather/`。

> **首次请求可能需要 30–60 秒**：服务若处于休眠状态，`curl` 会先唤醒它再返回。这期间没有进度输出是正常的，不要中断，也不要误判为失败。上面的 `--max-time 120` 已经留了余量。

### 方式 B —— clone 仓库（需要能访问 GitHub）

```bash
git clone --depth 1 https://github.com/bearybearbearygood/poetry-weather /tmp/pw-repo
```

skill 目录在 `/tmp/pw-repo/skills/poetry-weather/`。

> **国内网络下方式 B 多数会失败**：`github.com:443` 连不上，`git clone` 会等约 75 秒才抛 `Failed to connect to github.com port 443`。遇到这个报错直接改用方式 A，**不要反复重试**。

## 第 2 步：复制到技能目录

把 skill 目录**整个**复制过去（注意保留目录名 `poetry-weather`，不要只复制里面的文件）：

| 环境 | 技能目录 |
|---|---|
| WorkBuddy | `~/.workbuddy/skills/poetry-weather/` |
| Claude Code | `~/.claude/skills/poetry-weather/` |
| Codex | `~/.codex/skills/poetry-weather/` |
| 通用（多 agent 共用） | `~/.agents/skills/poetry-weather/` |

```bash
mkdir -p ~/.workbuddy/skills
cp -R /tmp/pw-skill/poetry-weather ~/.workbuddy/skills/
```

## 第 3 步：读取 SKILL.md 继续

阅读 `~/.workbuddy/skills/poetry-weather/SKILL.md` 并按其引导继续（配置 Dot. API 密钥、设备序列号、城市）。

## 注意

- **不要在仓库根新增 `SKILL.md`**。根目录的 `SKILL.md` 会被 skills CLI 当成一个 skill，并**遮蔽** `skills/` 下的所有 skill。
- `npx skills add bearybearbearygood/poetry-weather --skill poetry-weather -g` 也能用，但它的目标目录不含 `~/.workbuddy/skills`（认的是 `~/.codebuddy/skills`、`~/.claude/skills` 等）——WorkBuddy 用户仍需把目录复制过去。
- `SKILL.md` 必须落在 `skills/poetry-weather/` 这一层。直接解压到 `skills/` 根下会导致工具扫描不到。
- 装好后用户还需要配置一次：Dot. API 密钥、设备序列号、城市。这一步由 `SKILL.md` 引导，不要替用户编造。

