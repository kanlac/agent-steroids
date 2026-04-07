---
name: telegram-agents
description: |
  Configure and manage Telegram-connected Claude agents with heartbeat scheduling on macOS.
  Use when the user wants to: "set up Telegram agent", "add heartbeat", "configure Telegram channel",
  "管理 Telegram agent", "配置心跳", "添加定时任务", "Telegram 多 agent", "配置 Telegram",
  "添加 Telegram agent", "给 Telegram bot 创建身份", "设置定时任务", "新增定时任务",
  "每天X点执行Y", "schedule a task", "run this automatically", "set up a cron job",
  or encounters Telegram polling conflicts, 409 Conflict, file upload failures through proxy,
  or needs to add recurring/periodic automated task execution for Claude agents.
---

# Telegram Agents

让多个 Claude agent 各自绑定独立 Telegram bot，通过 tmux 常驻，配合 launchd 定时发送心跳消息。

> **时效性说明**：本 Skill 中的 workaround 针对 2026-03 已知问题。官方修复后部分方案可能不再需要，应用前先确认问题是否仍然存在。

## 架构

```
agents.yaml（统一配置）
      │
      ├── tmux: channel-<name> × N ──── Telegram Plugin（getUpdates + sendMessage）
      │         [Agent 身份文件]                   │
      │                                     Bot API（各自独立 token）
      │
      └── launchd（每分钟触发）
              │
          dispatcher.py
              │ 匹配 cron 表达式
              └── 心跳消息 → Telegram Bot API → channel session 接收处理
```

**三个核心原则**：
- **收发分离**：channel session 负责双向对话，其他 session 用 telegram-notify MCP 仅发通知
- **Bot 隔离**：每个 agent 独立 bot token + 独立状态目录，天然无 409 冲突
- **调度解耦**：dispatcher.py 不知道 Claude 存在，只做匹配时间 + 发 Telegram 消息

## 配置

`~/.config/telegram-agents/agents.yaml` 是唯一配置源：

```yaml
agents:
  sage:
    state_dir: telegram-sage       # 相对于 ~/.claude/channels/
    agent: sage                    # agent 身份 (~/.claude/agents/<name>.md)
    tmux: channel-sage             # tmux session 名
    dir: ~/projects/my-project     # 工作目录（claude 启动路径）
    heartbeats:
      - schedule: "0 9 * * *"     # 标准 5 字段 cron：分 时 日 月 周
        prompt: 早报摘要
      - schedule: "0 20 * * *"
        prompt: 晚间回顾

  default:
    state_dir: telegram            # 默认 agent 用 telegram/
    agent: my-assistant
    tmux: channel-default
    dir: ~
```

**常用 cron 表达式**：

| 表达式 | 含义 |
|---|---|
| `0 9 * * *` | 每天 9:00 |
| `0 */6 * * *` | 每 6 小时 |
| `0 9 * * 1-5` | 工作日 9:00 |
| `*/30 * * * *` | 每 30 分钟 |
| `0 0 1 * *` | 每月 1 号 0:00 |

## 心跳机制

dispatcher.py 每分钟被 launchd 触发，读取 agents.yaml，找到当前时间命中的 heartbeat，通过 Telegram Bot API 的 `sendMessage` 向对应的 channel session 发送消息。

消息格式：`[定时任务 YYYY-MM-DD HH:MM] <prompt>`

- **时间戳**：防止消息被去重忽略，保证每次触发都是独立事件
- **`[定时任务]` 前缀**：作为协议标记，让 agent 身份文件可以包含针对此前缀的特定处理指令

Agent 身份文件的系统提示词中应包含心跳处理说明，例如：
- 收到 `[定时任务]` 消息时自动开始执行对应任务
- 长期任务建议在开始时发 `/compact` 清理上下文，保持 token 开销可控

## Agent 身份

每个 channel session 绑定一个 agent 身份文件，赋予 bot 独立人格和能力范围。

**文件位置**：`~/.claude/agents/<name>.md`（全局）或 `.claude/agents/<name>.md`（项目内）

**格式**：

```markdown
---
name: sage
description: |
  <触发条件，支持 example 块>
model: inherit
color: purple
memory: user
---

<系统提示词：角色定义、能力范围、交流风格、心跳处理规则>
```

**注意事项**：
- `description` 多行内容**必须用 `|` block scalar**，否则解析失败、agent 无法加载
- `name` 只能用小写字母、数字和连字符（3-50 字符）
- `color` 只接受 8 种值：red, blue, green, yellow, purple, orange, pink, cyan
- `memory: user` 用于全局 agent（跨项目记忆），`memory: project` 用于项目 agent

## 首次安装

**目标**：launchd 每分钟调 dispatcher.py，dispatcher 读 agents.yaml 发心跳。

关键方向：
- 创建 `~/.config/telegram-agents/`，复制 `${SKILL_PATH}/scripts/dispatcher.py` 进去
- 创建 `~/Library/LaunchAgents/com.$USER.telegram-agents.plist`，每分钟触发，`StartInterval: 60`
- dispatcher 通过 `cat dispatcher.py | python3` 执行（绕过 macOS provenance 限制）

**关键陷阱**：

| 陷阱 | 原因 | 解决 |
|---|---|---|
| `AbandonProcessGroup: true` | launchd 主进程退出后会杀进程组，后台任务被终止 | plist 中加此键 |
| PATH 极简 | launchd 只有 `/usr/bin:/bin`，找不到 python3/pip 等 | plist 的 `EnvironmentVariables` 中补充 PATH |
| macOS provenance | Claude 创建的文件带 `com.apple.provenance`，launchd 拒绝直接执行 | `cat \| python3` 管道执行 |
| pyyaml 依赖 | dispatcher.py 用 `yaml` 模块 | 确认 `pip3 install pyyaml` |

## 添加 Agent

方向：BotFather 建 bot → 创建状态目录 → 写 agent 身份 → 更新 agents.yaml → 启动 tmux channel session。

**状态目录结构**：

```
~/.claude/channels/telegram-<name>/
├── .env          # TELEGRAM_BOT_TOKEN=... 和 TELEGRAM_CHAT_ID=...（chmod 600）
└── access.json   # 权限控制（allowFrom 列表）
```

**Channel session 启动命令模板**：

```bash
# 非默认 agent（name ≠ default）
TELEGRAM_STATE_DIR=~/.claude/channels/telegram-<name> \
  claude --channels 'plugin:telegram@claude-plugins-official' \
    --agent <agent-name> \
    --settings '{"enabledPlugins": {"telegram@claude-plugins-official": true}}'

# 默认 agent（name = default，状态目录用 telegram/）
claude --channels 'plugin:telegram@claude-plugins-official' \
  --agent <agent-name> \
  --settings '{"enabledPlugins": {"telegram@claude-plugins-official": true}}'
```

用 tmux 包裹保持常驻：`tmux new-session -d -s <session-name> "<command>"`

启动前检查 409 冲突：`ps eww` 查找已有 bun 进程使用同一 token，有则先 kill。

## 全局 Telegram 配置

- 从 `~/.claude/settings.json` 的 `enabledPlugins` 中**删除** `telegram@claude-plugins-official`（禁止普通 session 轮询），**不要卸载**插件本身
- 在 `~/.claude.json` 的 `mcpServers` 中注册 send-only 的 `telegram-notify` MCP，token 读取顺序：`$TELEGRAM_BOT_TOKEN` 环境变量 → `~/.claude/channels/telegram/.env`

## Bun Proxy 文件上传问题

> 仅影响使用 HTTP 代理的环境，无代理可跳过。

**现象**：通过 Telegram plugin 发送文件时报 `Network request for 'sendDocument' failed!`

**根因**：grammy 用 ReadableStream 构造 multipart body，Bun 1.3.x 的 fetch 在通过 proxy 发送 ReadableStream body 时有 TLS 记录排序 bug（[oven-sh/bun#17434](https://github.com/oven-sh/bun/issues/17434)）。文本消息不受影响。

**Workaround**：在 Telegram plugin 的 `server.ts` 中，用 undici 的 `fetch` + `ProxyAgent` 替代文件上传请求。不改 grammy 源码，plugin 更新后需重新应用。

**验证 Bun 是否已修复**：运行 `${SKILL_PATH}/scripts/test-bun-proxy-stream.sh <chat_id>`。输出 `FIXED` 则可移除 undici patch。

## 陷阱

- **409 Conflict**：同一 bot token 多个 session 轮询会冲突。多 agent 方案中每个 agent 独立 token，无此问题。单 agent 场景中，普通 session 全局禁用插件可防止误启轮询
- **AbandonProcessGroup**：launchd plist 必须加 `AbandonProcessGroup: true`，否则 dispatcher 后台化任务后主进程退出，后台任务被立即终止
- **macOS provenance**：Claude Code 创建的脚本文件带 `com.apple.provenance` 扩展属性，launchd 无法直接执行。用 `cat | python3`（dispatcher）和 `echo | bash`（shell 任务）绕过
- **launchd PATH**：launchd 环境 PATH 极简，plist 中必须显式补充 Homebrew 路径和 `~/.local/bin`
