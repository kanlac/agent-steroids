# agent-steroids

Claude Code 通用增强插件，提供可复用的 Skills、Commands、Agents、Hooks 和 MCP Servers。

## 安装

```bash
claude plugin marketplace add kanlac/agent-steroids
claude plugin install steroids@agent-steroids
```

## 包含内容

### Skills

| Skill | 说明 |
|-------|------|
| `cdp-chrome` | 共享有头 Chrome 实例管理。所有需要 GUI 浏览器的场景（社交媒体、登录态网站、反 bot 页面）必须遵循此 Skill。含启动脚本和 MCP 配置模板。 |
| `telegram-agents` | Telegram agent 配置与管理。包括 tmux 会话、Telethon 调度器、launchd 心跳定时任务。 |
| `extract-to-md` | 将网页导出内容或 PDF 报告重构为可编辑 Markdown。处理断行修复、段落结构恢复、图片插入等。 |
| `read-book` | EPUB 书籍中英双语翻译，以及阅读和讨论书籍内容。 |
| `wechat-desktop` | 通过 computer-use MCP 在 macOS 上读取、浏览和总结微信群聊消息。 |

### Commands

| 命令 | 说明 |
|------|------|
| `/check-release` | 检查 Claude Code 版本更新，通过 Telegram 发送发布报告或 Anthropic 新闻简报。 |
| `/song <query>` | 搜索歌词、翻译为中文，收集趣闻和流行文化梗。 |
| `/task-init <name>` | 创建任务目录并编写需求文档。 |
| `/task-run <name>` | 启动开发-评估反馈循环。 |
| `/tg-status` | 查看所有 Telegram agent 的运行状态。 |
| `/tg-restart <agent>` | 重启指定 Telegram agent 的 channel 会话。 |
| `/tg-logs [lines]` | 查看心跳调度器日志。 |

### Agents

| Agent | 说明 |
|-------|------|
| `developer` | 根据需求和反馈执行开发任务。 |
| `evaluator` | 对照需求评估开发成果并运行测试。 |
| `reviewer` | 审查指定的代码变更。 |

### Hooks

| Hook | 说明 |
|------|------|
| `guard-payload-size` | 会话 payload 接近 20MB API 限制时告警，提示执行 `/compact`。临时方案，待官方修复后可移除。 |

### MCP Servers

| Server | 说明 |
|--------|------|
| `telegram-notify` | 轻量级 Telegram 通知服务，供 agent 发送消息。 |

## 项目结构

```
agent-steroids/
  .claude-plugin/       # 插件清单和 marketplace 配置
  skills/               # 自包含的方法论文档（含脚本）
  commands/             # 斜杠命令（frontmatter 驱动）
  agents/               # 子 agent 定义
  hooks/                # 事件驱动的自动化
  mcp-servers/          # MCP 服务器实现
  docs/
    tech/               # 技术方案和架构设计
    research/           # 调研、对比分析
```

## License

MIT
