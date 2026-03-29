# 计划：Telegram Send-Only MCP Server

> 日期：2026-03-29
> 背景调研：[../research/20260329-telegram-multi-session.md](../research/20260329-telegram-multi-session.md)

## 目标

实现一个极简的 Telegram send-only MCP server，全局可用，仅提供消息发送能力，不轮询。配合 `--settings` 按需启用完整 Telegram 插件（仅频道 session），解决多 session 轮询冲突。

## Phase 1：编写 send-only MCP server

在 Agent Steroids 项目中创建 MCP server。

**文件**：`mcp-servers/telegram-notify/server.ts`

**工具定义**：
- `telegram_notify` — 向指定 chat_id 发送文本消息
  - 参数：`chat_id`（必填）、`text`（必填）
  - 调用 Telegram Bot API `sendMessage` endpoint
  - 支持基础 Markdown 格式（`parse_mode: "Markdown"`）

**Token 读取**：
- 优先 `$TELEGRAM_BOT_TOKEN` 环境变量
- 回退读取 `~/.claude/channels/telegram/.env`

**技术选型**：
- 运行时：Bun（与完整插件一致）
- MCP SDK：`@modelcontextprotocol/sdk`
- HTTP 请求：直接 `fetch`，无额外依赖

**验证**：手动启动 server，通过 MCP inspector 调用 `telegram_notify`，确认消息送达 ✅

## Phase 2：全局注册 send-only MCP

编辑 `~/.config/agents.json`（bootstrap 配置源），添加 telegram-notify MCP server 配置。

运行 `yadm bootstrap` 或手动更新 `~/.claude.json`：

```json
{
  "mcpServers": {
    "telegram-notify": {
      "command": "bun",
      "args": ["run", "--cwd", "<mcp-server-path>", "server.ts"]
    }
  }
}
```

**验证**：启动新 Claude Code session，确认 `telegram_notify` 工具可用 ✅

## Phase 3：从全局启用中移除 Telegram 插件

从 `~/.claude/settings.json` 的 `enabledPlugins` 中**删除** `telegram@claude-plugins-official` 条目。

**保留安装**：不动 `installed_plugins.json`，插件仍在 marketplace cache 中，正常接收更新。仅移除启用状态，使普通 session 不加载、不轮询。

**验证**：启动普通 session，确认不再轮询 Telegram（无 `polling as @xxx` 日志）✅

## Phase 4：频道 session 配置

通过 `--settings` 在 session 级重新启用完整 Telegram 插件：

```bash
claude --channels 'plugin:telegram@claude-plugins-official' \
  --settings '{"enabledPlugins": {"telegram@claude-plugins-official": true}}'
```

> 已实测验证：`--settings` 的 `enabledPlugins` 可在 session 级启用全局未启用的已安装插件。插件走正常 marketplace 更新，无需 `--plugin-dir` 或手动拷贝。

可将此命令封装为 alias 或脚本，避免每次手打。

**验证**：
1. 频道 session 正常轮询，收到 Telegram 消息 ✅
2. 其他 session 不轮询，无 409 错误 ✅
3. 其他 session 可通过 `telegram_notify` 发送通知 ✅

## Phase 5：端到端测试

1. 启动频道 session（带 `--channels` + `--settings`）
2. 同时启动 2 个普通 session
3. 从 Telegram 发消息 → 仅频道 session 收到
4. 在普通 session 中调用 `telegram_notify` → Telegram 收到通知
5. 持续运行 5 分钟，检查无 409 Conflict 日志

**验证**：以上 5 项全部通过 ✅
