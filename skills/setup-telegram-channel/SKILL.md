---
name: setup-telegram-channel
description: Configure Claude Code's Telegram Channel for bidirectional messaging. Set up dedicated channel sessions (long polling) alongside send-only notification for other sessions. Supports multiple agents with independent bots. Use when the user asks to "set up Telegram channel", "configure Telegram", "add Telegram agent", "fix Telegram not receiving messages", "Telegram zombie processes", "Telegram 多 session 冲突", "配置 Telegram", "添加 Telegram agent", or encounters Telegram polling conflicts or file upload failures through proxy.
---

# Telegram Channel 配置

让 Claude Code 通过 Telegram 接收和回复消息。核心思路：**收发分离**——专用 channel session 负责双向对话，其他 session 只能发通知。支持多个 agent 各自绑定独立 bot。

> **时效性说明**：本 Skill 中的 workaround 是针对当前（2026-03）Claude Code Telegram plugin 和 Bun 的已知问题。如果官方修复了多 session 冲突或 Bun 修复了 proxy bug，这些方案可能不再需要。应用前先确认问题是否仍然存在。

## 架构

### 单 Agent（基础）

```
┌──────────────────────────┐     ┌─────────────────────────────┐
│  普通 Claude Code (×N)    │     │  专用 Channel Session (×1)   │
│                          │     │  (tmux 常驻)                 │
│  telegram-notify MCP     │     │  Telegram Plugin (完整)       │
│  (send-only, 不轮询)     │     │  (双向, long polling)         │
└───────────┬──────────────┘     └────────────┬────────────────┘
            │ sendMessage                     │ getUpdates + sendMessage
            └─────────────┬───────────────────┘
                          ▼
                   Telegram Bot API
```

### 多 Agent

每个 agent 对应一个独立的 Telegram bot + channel session。通过 `TELEGRAM_STATE_DIR` 环境变量隔离状态目录，各 bot 独立轮询，天然无 409 冲突。

```
telegram-notify MCP ──── 默认 bot (广播通知)
(send-only, 所有 session 共享)

tmux: channel-default ── Telegram Plugin ── Bot Default (getUpdates)
                         STATE_DIR: ~/.claude/channels/telegram/

tmux: channel-sage ───── Telegram Plugin ── Bot Sage (getUpdates)
                         STATE_DIR: ~/.claude/channels/telegram-sage/

tmux: channel-xxx ────── Telegram Plugin ── Bot XXX (getUpdates)
                         STATE_DIR: ~/.claude/channels/telegram-xxx/
```

**状态目录结构**：

```
~/.claude/channels/
├── telegram/                # 默认 agent
│   ├── .env                 # TELEGRAM_BOT_TOKEN=...
│   └── access.json          # 权限控制
├── telegram-sage/           # Sage agent
│   ├── .env
│   └── access.json
└── telegram-<name>/         # 更多 agent...
    ├── .env
    └── access.json
```

**关键约束**：Telegram Bot API 的 `getUpdates` 只允许一个消费者。同一 bot token 多个 session 轮询会 409 Conflict。多 agent 方案中每个 bot 独立，不存在此问题。

## 前置：清理 MCP 僵尸进程

配置前**必须**先检查是否有旧的 Telegram MCP 僵尸进程。它们会抢占 polling slot，导致新 channel session 收不到消息。

查找僵尸进程：
```bash
ps aux | grep -E 'bun run.*(telegram.*start)' | grep -v grep | grep -v 'telegram-notify'
```

**只清理 bun telegram MCP 进程，绝不能清理 claude 进程本身。** 识别方法：僵尸进程的命令是 `bun run --cwd .../telegram ...start`，而 claude 进程是 `claude ...`。

清理时保留当前 session 的进程（通过 TTY 或 PID 区分），kill 其余的。清理后确认只剩 0 或 1 个 telegram MCP 进程。

## 配置方向

### 1. 全局禁用 Telegram Plugin

从 `~/.claude/settings.json` 的 `enabledPlugins` 中删除 `telegram@claude-plugins-official`。**保留安装**（不动 `installed_plugins.json`），插件仍走 marketplace 正常更新。

目的：普通 session 启动时不加载插件、不轮询。

### 2. 全局注册 Send-Only MCP

注册一个极简的 telegram-notify MCP server 到 `~/.claude.json` 的 `mcpServers`。这个 server 只调 `sendMessage` API，不做 polling。所有 session 都能发通知，零冲突。

token 读取顺序：`$TELEGRAM_BOT_TOKEN` 环境变量 → `~/.claude/channels/telegram/.env`。

### 3. 频道 Session 启动

推荐用 `--agent` 为每个 channel session 指定一个预定义 agent，赋予其专属人格和能力。`--agent` 覆盖 session 的默认 agent 设置，可在 `~/.claude/settings.json` 的 `agents` 中定义，也可通过 `--agents` flag 内联传入 JSON。

#### 单 Agent（默认）

```bash
claude --channels 'plugin:telegram@claude-plugins-official' \
  --agent my-agent \
  --settings '{"enabledPlugins": {"telegram@claude-plugins-official": true}}'
```

`--settings` 的 `enabledPlugins` 可在 session 级启用全局未启用的已安装插件，不需要 `--plugin-dir`。

#### 多 Agent

每个 agent 需要：
1. 在 @BotFather 创建独立 bot，获取 token
2. 创建状态目录 `~/.claude/channels/telegram-<name>/`，写入 `.env`（token + chat_id）和 `access.json`
3. 通过 `TELEGRAM_STATE_DIR` 指定状态目录、`--agent` 指定 agent 启动 channel session

```bash
# Agent A（使用默认状态目录）
claude --channels 'plugin:telegram@claude-plugins-official' \
  --agent agent-a \
  --settings '{"enabledPlugins": {"telegram@claude-plugins-official": true}}'

# Agent B（指定独立状态目录 + 独立 bot）
TELEGRAM_STATE_DIR=~/.claude/channels/telegram-<name> \
  claude --channels 'plugin:telegram@claude-plugins-official' \
    --agent agent-b \
    --settings '{"enabledPlugins": {"telegram@claude-plugins-official": true}}'
```

`.env` 文件权限应设为 600：`chmod 600 ~/.claude/channels/telegram-<name>/.env`

### 4. tmux 常驻 Channel Session

用 tmux 保持 channel session 持久运行。多 agent 时为每个 agent 开独立 tmux session：

```bash
# Agent A
tmux new-session -d -s channel-a \
  "claude --channels 'plugin:telegram@claude-plugins-official' \
    --agent agent-a \
    --settings '{\"enabledPlugins\":{\"telegram@claude-plugins-official\":true}}'"

# Agent B（示例：Sage）
tmux new-session -d -s channel-sage \
  "TELEGRAM_STATE_DIR=\$HOME/.claude/channels/telegram-sage \
   claude --channels 'plugin:telegram@claude-plugins-official' \
     --agent sage \
     --settings '{\"enabledPlugins\":{\"telegram@claude-plugins-official\":true}}'"
```

## Bun Proxy 文件上传问题

> **仅影响使用 HTTP 代理的环境。** 无代理可跳过此节。

在 HTTP 代理环境下，通过 Telegram plugin 发送文件会失败：`Network request for 'sendDocument' failed!`

**根因**：grammy 用 ReadableStream 构造 multipart body，而 Bun 1.3.x 的 fetch 在通过 proxy 发送 ReadableStream body 时有 TLS 记录排序 bug（[oven-sh/bun#17434](https://github.com/oven-sh/bun/issues/17434)）。文本消息不受影响。

**Workaround**：在 Telegram plugin 的 `server.ts` 中，用 undici 的 `fetch` + `ProxyAgent` 替代文件上传请求：

1. 在 plugin 目录 `bun add undici`
2. 添加 `import { fetch as undiciFetch, ProxyAgent } from 'undici'`
3. 写一个 `sendFileViaUndici()` helper，用原生 FormData + undici fetch 发文件
4. 替换 reply tool 中的文件发送循环，改调 helper

不改 grammy 源码，不影响文本消息。plugin 更新后需重新应用（代码会被覆盖）。

**验证 Bun 是否已修复**：运行 [scripts/test-bun-proxy-stream.sh](scripts/test-bun-proxy-stream.sh)，如果输出 `FIXED` 则可移除 undici patch。

**详细技术调研**：
- [多 Session 冲突调研](https://github.com/kanlac/agent-steroids/blob/main/docs/research/20260329-telegram-multi-session.md)
- [Bun Proxy 文件上传 Bug 调研](https://github.com/kanlac/agent-steroids/blob/main/docs/research/20260329-bun-proxy-file-upload.md)
