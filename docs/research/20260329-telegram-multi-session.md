# Telegram 多 Session 冲突问题调研与方案

> 日期：2026-03-29

## 背景

使用 Claude Code 时，Telegram 插件（`telegram@claude-plugins-official`）在 `settings.json` 中全局启用。每个 Claude Code session 启动时都会加载该插件的 MCP server，MCP server 启动后**无条件开始长轮询**（`bot.start()` → grammy 的 `getUpdates`）。

Telegram Bot API 的 `getUpdates` **只允许一个消费者**——多个消费者同时轮询会触发 409 Conflict。插件内置了指数退避重试（最高 15s），但多个 session 会持续竞争，导致：

- 消息被随机 session 抢走，而非固定的 `--channels` session
- 频繁的 409 错误日志
- 消息丢失或延迟

## 需求

- **所有 session** 都能向 Telegram **发送**通知
- **仅一个固定 session**（带 `--channels` 的）**接收** Telegram 消息

## 现有架构分析

### 轮询机制

- 文件：`~/.claude/plugins/cache/claude-plugins-official/telegram/0.0.4/server.ts`
- 使用 grammy 库的 `bot.start()` 启动长轮询
- **无条件启动**，没有环境变量或配置可以跳过轮询
- 409 Conflict 时自动重试（指数退避，attempt 1 = 1s，上限 15s）

### 插件加载机制

- 全局启用的插件对所有 session 生效
- `--plugin-dir` 可以按 session 指定额外插件目录（**扩展**，非替换）
- `--channels plugin:telegram@claude-plugins-official` 控制是否处理入站消息，但不影响 MCP server 是否启动轮询

### Session 级插件控制机制

| 机制 | session 级控制 | 说明 |
|------|---------------|------|
| `--settings '{"enabledPlugins": {...}}'` | **可以** | CLI 直接覆盖 settings，最精确 |
| `--plugin-dir <path>` | 可以（仅扩展） | 只能加不能减，只接受目录路径 |
| `--bare` | 可以（太粗暴） | 跳过几乎所有基础设施 |
| 项目级 `.claude/settings.json` | 按项目 | `enabledPlugins` 可覆盖全局 |
| `settings.local.json` | 持久化 | 非 per-session |
| `CLAUDE_CONFIG_DIR` 等环境变量 | **不存在** | 配置目录硬编码 `~/.claude/` |

### 结论

**现有架构无法分离收/发**——加载插件 = 启动 MCP server = 开始轮询。需要组合使用 send-only MCP + session 级插件控制。

## 实测验证

### 测试 1：`--channels` 是否自动加载未启用的插件

```bash
# 从 enabledPlugins 中删除 telegram 后
claude --channels 'plugin:telegram@claude-plugins-official' -p '列出 telegram 工具'
```

**结果：无 telegram 工具** — `--channels` 不自动加载未启用的插件。

### 测试 2：`--settings` 能否 session 级启用插件

```bash
claude --channels 'plugin:telegram@claude-plugins-official' \
  --settings '{"enabledPlugins": {"telegram@claude-plugins-official": true}}' \
  -p '列出 telegram 工具'
```

**结果：4 个工具全部可用**（reply、react、edit_message、download_attachment）。

### 结论

`--settings` 可以在 session 级精确控制 `enabledPlugins`，无需 `--plugin-dir`，插件走正常 marketplace 更新链路。

## 方案评估

### 方案 A：全局 send-only MCP + `--settings` 按需启用 ✅ 选定

1. 从 `settings.json` 的 `enabledPlugins` 中删除 `telegram@claude-plugins-official`（保留安装，marketplace 正常更新）
2. 编写极简 send-only MCP server（仅 `sendMessage` API 调用，不轮询），全局注册到 `~/.claude.json`
3. 频道 session 通过 `--settings` 按需启用完整插件

**频道 session 启动命令**：
```bash
claude --channels 'plugin:telegram@claude-plugins-official' \
  --settings '{"enabledPlugins": {"telegram@claude-plugins-official": true}}'
```

**优点**：完全解耦，零冲突，send-only 极简（30-50 行），插件正常更新，不依赖 `--plugin-dir` 和 cache 路径
**缺点**：send-only 只支持基础发送，不含 react/edit/附件等高级功能（可接受，仅用于通知推送）

### 方案 B：iMessage 全局推送 + Telegram 仅特定 session

**优点**：不需要额外代码
**缺点**：其他 session 无法发 Telegram；两个通知渠道增加认知负担

### 方案 C：Fork 插件，增加 `TELEGRAM_NO_POLL` 环境变量

**优点**：改动最小（3-5 行），所有 session 用同一套完整工具
**缺点**：需维护 fork，官方更新需手动同步

### 方案 D：双 Bot Token

**优点**：零代码改动
**缺点**：用户在 Telegram 端看到不同 bot 发消息，体验割裂
