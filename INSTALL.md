# Agent Steroids 安装手册

这份文件是唯一的安装入口。让任意 coding agent 安装本仓库时，先让它读取本文件，再按目标 runtime 执行对应部分。

默认仓库源：`kanlac/agent-steroids`。

## 安装原则

1. 优先使用各 runtime 的插件/marketplace 机制，不要手工复制一份 `skills/` 目录。
2. 默认只安装 `steroids` 主插件；只有需要持久登录态、人工 CAPTCHA、live site inspection 等 `headed-browser` 能力时才安装 `chrome`。
3. `telegram` 是 **Claude Code 专用** 插件；不要在 Codex 或 Hermes 中安装/启用 Telegram 插件。
4. 如果 marketplace 或插件已经存在，不要当作失败；继续执行安装、更新或验证步骤。

## Runtime 选择表

| Runtime | 默认安装 | 可选安装 | 不安装 |
|---|---|---|---|
| Claude Code | `steroids` | `chrome`, `telegram`, `write-blog`, `taskdag` | 无 |
| Codex | `steroids` | `chrome`, `taskdag` | `telegram`, `write-blog` |
| Hermes | `agent-steroids/steroids` | `agent-steroids/chrome` | `agent-steroids/telegram`, `agent-steroids/write-blog`, `agent-steroids/taskdag` |

## Claude Code

适用场景：Claude Code 使用本仓库的 skills、commands、hooks、MCP server。

```bash
claude plugin marketplace add kanlac/agent-steroids
claude plugin install steroids@agent-steroids
```

按需安装：

```bash
claude plugin install chrome@agent-steroids      # 可选：共享有头 Chrome/CDP provider
claude plugin install telegram@agent-steroids    # Claude Code 专用：Telegram agent 运维 + payload guard
claude plugin install write-blog@agent-steroids  # Claude Code 专用：写作流程 skill
claude plugin install taskdag@agent-steroids     # 可选：ADR + Task DAG 控制面
```

验证：

```bash
claude plugin list
```

## Codex

适用场景：Codex 使用跨运行时稳定的 skill 插件。Codex marketplace 只暴露 `steroids`、`chrome` 和 `taskdag`。

```bash
codex plugin marketplace add kanlac/agent-steroids
codex plugin add steroids@agent-steroids
```

按需安装：

```bash
codex plugin add chrome@agent-steroids           # 可选：共享有头 Chrome/CDP provider
codex plugin add taskdag@agent-steroids          # 可选：ADR + Task DAG 控制面
```

验证：

```bash
codex plugin list
```

## Hermes

适用场景：Hermes 通过根目录 shim 暴露可单独启用的子插件。不要启用根 `agent-steroids`，只启用需要的子插件。

```bash
hermes plugins install kanlac/agent-steroids --no-enable
hermes plugins enable agent-steroids/steroids
```

按需启用：

```bash
hermes plugins enable agent-steroids/chrome      # 可选：共享有头 Chrome/CDP provider skill
```

验证：

```bash
hermes plugins list --plain --no-bundled
```

Hermes 加载 skill 时使用插件命名空间，而不是 enable key：

```bash
hermes -s steroids:paper-download
hermes -s chrome:cdp-chrome
```

启用/禁用插件后，启动新 session 或重启 gateway 才会生效。

## 安装后检查

安装 agent 应确认：

1. 目标 runtime 的插件列表里能看到刚安装的插件。
2. 只安装了该 runtime 支持的插件；尤其是 Codex/Hermes 中不应出现 `telegram`。
3. 如安装 `chrome`，Claude Code / Codex 会随插件加载 `cdp-chrome` MCP launcher；继续根据 `plugins/chrome/skills/cdp-chrome/SKILL.md` 在 steroids 配置文件（macOS/Linux: `~/.config/steroids.json`；Windows: `%APPDATA%\steroids.json`）设置当前 OS 用户专属的 `cdp-chrome.port/profile_dir`，运行 `plugins/chrome/skills/cdp-chrome/scripts/doctor.sh` 验证，再用 `start.sh` 启动。Hermes 支持 MCP，但需按该 skill 在 `mcp_servers` 中手动注册。
4. 如安装 Claude Code 的 `telegram`，继续根据 `plugins/telegram/skills/telegram-agents/SKILL.md` 完成 Telegram agent 配置。
