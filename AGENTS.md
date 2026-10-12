# AGENTS.md

本仓库同时是一个 **agent skill 仓库**。用户在对话里说「帮我安装这个 skill：https://github.com/bearybearbearygood/poetry-weather」时，按下面的步骤操作。

## 安装步骤

1. 克隆仓库（浅克隆即可）：
   ```bash
   git clone --depth 1 https://github.com/bearybearbearygood/poetry-weather /tmp/poetry-weather
   ```
2. 把 `skills/poetry-weather/` **整个目录**复制到用户的技能目录：

   | 环境 | 技能目录 |
   |---|---|
   | WorkBuddy | `~/.workbuddy/skills/poetry-weather/` |
   | Claude Code | `~/.claude/skills/poetry-weather/` |
   | Codex | `~/.codex/skills/poetry-weather/` |
   | 通用（多 agent 共用） | `~/.agents/skills/poetry-weather/` |

   ```bash
   mkdir -p ~/.workbuddy/skills
   cp -R /tmp/poetry-weather/skills/poetry-weather ~/.workbuddy/skills/
   ```
3. 清理临时克隆，然后阅读 `~/.workbuddy/skills/poetry-weather/SKILL.md` 并按其引导继续。

## 注意

- **不要在仓库根新增 `SKILL.md`**。根目录的 `SKILL.md` 会被 skills CLI 当成一个 skill，并**遮蔽** `skills/` 下的所有 skill。
- `npx skills add bearybearbearygood/poetry-weather --skill poetry-weather -g` 也能用，但它的目标目录不含 `~/.workbuddy/skills`（认的是 `~/.codebuddy/skills`、`~/.claude/skills` 等）——WorkBuddy 用户仍需把目录复制过去。
- 装好后用户还需要配置一次：Dot. API 密钥、设备序列号、城市。这一步由 `SKILL.md` 引导，不要替用户编造。
