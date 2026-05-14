# agent-steroids

Claude Code / Codex 通用增强插件，提供可复用的 Skills、Commands、Agents、Hooks 和 MCP Servers。

## 安装

### Claude Code

```bash
claude plugin marketplace add kanlac/agent-steroids
claude plugin install steroids@agent-steroids
```

### Codex

仓库根目录包含 `.agents/plugins/marketplace.json`；Codex marketplace 中的 `steroids` plugin 指向 `plugins/steroids/`，安装后会暴露 `plugins/steroids/skills/` 下的通用 Skills。

当前 Codex manifest 只声明跨运行时稳定可用的 Skills；Commands、Agents、Hooks 和 MCP Servers 保留 Claude Code 插件结构，避免在 Codex 中加载 Claude 专用 hook 环境变量。

## 包含内容

### Skills

| Skill | 说明 |
|-------|------|
| [`cdp-chrome`](plugins/steroids/skills/cdp-chrome/SKILL.md) | 共享有头 Chrome 实例管理。所有需要 GUI 浏览器的场景（社交媒体、登录态网站、反 bot 页面）必须遵循此 Skill。含启动脚本和 MCP 配置模板。 |
| [`telegram-agents`](plugins/steroids/skills/telegram-agents/SKILL.md) | Telegram agent 配置与管理。包括 tmux 会话、Telethon 调度器、launchd 心跳定时任务。 |
| [`extract-to-md`](plugins/steroids/skills/extract-to-md/SKILL.md) | 将网页导出内容或 PDF 报告重构为可编辑 Markdown。处理断行修复、段落结构恢复、图片插入等。 |
| [`read-book`](plugins/steroids/skills/read-book/SKILL.md) | EPUB 书籍中英双语翻译，以及阅读和讨论书籍内容。 |
| [`wechat-desktop`](plugins/steroids/skills/wechat-desktop/SKILL.md) | 通过 computer-use MCP 在 macOS 上读取、浏览和总结微信群聊消息。 |
| [`html-to-pdf`](plugins/steroids/skills/html-to-pdf/SKILL.md) | 将样式化 HTML 转为高质量单页 PDF。自动处理动态元素（scroll-snap、CSS 动画、IntersectionObserver），含可复用生成脚本。 |
| [`clipping`](plugins/steroids/skills/clipping/SKILL.md) | 将网页文章保存为本地 Markdown 笔记。支持微信公众号等 JS 渲染页面，对信息图/表格截图使用 PaddleOCR 提取文本并重构为 Markdown 表格。 |
| [`paper-download`](plugins/steroids/skills/paper-download/SKILL.md) | 学术论文下载。三级策略：OA 直链、出版商页面导航、知网登录。支持 arXiv、Springer、MDPI、知网等主流平台。 |

### Commands

| 命令 | 说明 |
|------|------|
| [`/check-release`](plugins/steroids/commands/check-release.md) | 检查 Claude Code 版本更新，通过 Telegram 发送发布报告或 Anthropic 新闻简报。 |
| [`/song <query>`](plugins/steroids/commands/song.md) | 搜索歌词、翻译为中文，收集趣闻和流行文化梗。 |
| [`/task-init <name>`](plugins/steroids/commands/task-init.md) | 创建任务目录并编写需求文档。 |
| [`/task-run <name>`](plugins/steroids/commands/task-run.md) | 启动开发-评估反馈循环。 |
| [`/tg-status`](plugins/steroids/commands/tg-status.md) | 查看所有 Telegram agent 的运行状态。 |
| [`/tg-restart <agent>`](plugins/steroids/commands/tg-restart.md) | 重启指定 Telegram agent 的 channel 会话。 |
| [`/tg-logs [lines]`](plugins/steroids/commands/tg-logs.md) | 查看心跳调度器日志。 |

### Agents

| Agent | 说明 |
|-------|------|
| [`reviewer`](plugins/steroids/agents/reviewer.md) | 审查指定的代码变更。 |

### Hooks

| Hook | 说明 |
|------|------|
| [`guard-payload-size`](plugins/steroids/hooks/guard-payload-size.sh) | 会话 payload 接近 20MB API 限制时告警，提示执行 `/compact`。临时方案，待官方修复后可移除。 |

### Scripts

| 脚本 | 说明 |
|------|------|
| [`agent-switch`](scripts/agent-switch) | 切换本机 agent CLI 账号。当前支持 Codex：`agent-switch` 与 `agent-switch codex` 等价，显示当前 live auth 账号和账号快照列表，共享 `~/.codex` 配置、skills、sessions，仅切换账号认证快照；`agent-switch codex logout` 保存当前账号并移除 live auth，便于重新 `codex login`；切换前检查 Codex CLI、Codex.app 和 `codex-acp` 进程，`--force` 可先结束这些进程再继续。`agent-switch install` 一键 symlink 到 `~/.local/bin`。 |
| [`chrome-instances`](scripts/chrome-instances) | 管理 macOS 上的多 Chrome 实例。列出所有实例及其 Profile/窗口，按 PID 或名称聚焦窗口。通过 AppleScript 解析窗口标题，无需调试端口。`chrome-instances install` 一键 symlink 到 `~/.local/bin`。 |

### MCP Servers

| Server | 说明 |
|--------|------|
| [`telegram-notify`](plugins/steroids/mcp-servers/telegram-notify/) | 轻量级 Telegram 通知服务，供 agent 发送消息。 |

## 项目结构

```
agent-steroids/
  .agents/plugins/      # Codex marketplace 配置
  .claude-plugin/       # Claude marketplace 配置
  scripts/              # 独立 CLI 工具
  plugins/steroids/     # Claude / Codex 共用插件包
    .claude-plugin/     # Claude 插件清单
    .codex-plugin/      # Codex 插件清单
    skills/             # 自包含的方法论文档（含脚本）
    commands/           # 斜杠命令（frontmatter 驱动）
    agents/             # 子 agent 定义
    hooks/              # 事件驱动的自动化
    mcp-servers/        # MCP 服务器实现
  docs/
    tech/               # 技术方案和架构设计
    research/           # 调研、对比分析
```

## License

MIT
