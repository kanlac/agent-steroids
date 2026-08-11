# agent-steroids

Claude Code / Codex / Hermes 通用增强插件集合。这个仓库同时兼容三种 agent runtime，但各插件的 runtime 覆盖不同。插件按用途分类，方便在不同环境中按需启用：

- `steroids`：主体 Skills 和通用 workflow。
- `telegram`：Claude Code 专用的 Telegram agent 运维、通知 MCP、Telegram hook，并包含 `guard-payload-size`。
- `chrome`：可选的每 OS 用户一个进程的共享有头 Chrome provider；Claude Code / Codex 安装后随插件提供 `cdp-chrome` MCP 启动器。
- `write-blog`：Claude Code 专用的写作流程 skill 插件——选题构思、对话式挖掘、大纲迭代、按作者风格成文，附信息图/制图参考。

`steroids` 和 `chrome` 的 canonical skills 位于 `plugins/<plugin>/skills/` 并可跨 runtime 复用；Claude Code / Codex 通过各自 marketplace 安装，Hermes 通过根目录 shim 仅暴露 `steroids` 与 `chrome`。`telegram` 和 `write-blog` 保持 Claude Code 专用，不提供 Codex marketplace 条目或 Hermes shim。

## 安装

安装、升级、启用流程统一见 [`INSTALL.md`](INSTALL.md)。如果让 agent 帮你安装，直接让它先读取这份安装手册即可。

## 插件拆分与依赖

详细设计见 [`docs/tech/20260518-plugin-split.md`](docs/tech/20260518-plugin-split.md)。核心原则：插件之间优先依赖能力（capability），不要把 provider 写死成硬依赖。例如 `paper-download` 需要 `headed-browser` 能力，但不一定需要安装 `chrome/cdp-chrome`；如果用户环境已有 Codex Chrome plugin 或原生 browser-use，就可以直接使用现有 provider。

| Plugin | Runtime | 包含内容 | 硬依赖 | 可选 / capability 依赖 |
|---|---|---|---|---|
| [`steroids`](plugins/steroids/) | Claude + Codex + Hermes | 主体 Skills：文档处理、书籍阅读、PDF 导出、网页剪藏、论文下载、微信桌面 workflow、Agent 记忆管理（诊断/整理/吸收），以及 `/song` | 无 | `paper-download` / `clipping` 的登录态或 CAPTCHA 场景需要 `headed-browser`；`wechat-desktop` 需要 macOS + computer-use MCP |
| [`telegram`](plugins/telegram/) | Claude Code only | `telegram-agents`、`/tg-*`、`/check-release`、`telegram-notify` MCP、Telegram time hook、`guard-payload-size` hook | Claude Code + official Telegram plugin；心跳 workflow 需 Telethon/tmux/launchd | 无 |
| [`chrome`](plugins/chrome/) | Claude + Codex + Hermes | `cdp-chrome` 每 OS 用户一个进程的共享有头 Chrome provider；Claude/Codex 内置 `cdp-chrome` MCP 启动器，会读取当前用户 steroids 配置 | Chrome、`npx`；Hermes 使用时需在 `mcp_servers` 注册 | 提供 `headed-browser`，可被 Codex Chrome plugin / 原生 browser-use 替代 |
| [`write-blog`](plugins/write-blog/) | Claude Code only | `write-blog` skill：选题/对话式挖掘/大纲迭代/按作者风格成文，附 voice-dna 与制图参考 | 无 | 无 |

## Skills

| Skill | Plugin | 说明 |
|-------|--------|------|
| [`extract-to-md`](plugins/steroids/skills/extract-to-md/SKILL.md) | `steroids` | 将网页导出内容或 PDF 报告重构为可编辑 Markdown。处理断行修复、段落结构恢复、图片插入等。 |
| [`read-book`](plugins/steroids/skills/read-book/SKILL.md) | `steroids` | EPUB 书籍中英双语翻译，以及阅读和讨论书籍内容。 |
| [`youtube-bilingual-transcript`](plugins/steroids/skills/youtube-bilingual-transcript/SKILL.md) | `steroids` | 把 YouTube 链接转成中英对照单页 HTML 阅读稿。yt-dlp 抓字幕+章节，agent 翻译并策展，脚本渲染带时间戳跳转、带序号章节目录、重点高亮、专有名词内联点击注释。 |
| [`html-to-pdf`](plugins/steroids/skills/html-to-pdf/SKILL.md) | `steroids` | 将样式化 HTML 转为高质量单页 PDF。自动处理动态元素（scroll-snap、CSS 动画、IntersectionObserver），含可复用生成脚本。 |
| [`clipping`](plugins/steroids/skills/clipping/SKILL.md) | `steroids` | 将网页文章保存为本地 Markdown 笔记。支持微信公众号等 JS 渲染页面；对信息图/表格截图可使用 PaddleOCR 提取文本并重构为 Markdown 表格。 |
| [`paper-download`](plugins/steroids/skills/paper-download/SKILL.md) | `steroids` | 学术论文检索与下载。三级策略：HTTP/OA 直链、headless 解析、headed browser 登录/CAPTCHA。`cdp-chrome` 只是可选 provider。 |
| [`wechat-desktop`](plugins/steroids/skills/wechat-desktop/SKILL.md) | `steroids` | 通过 computer-use MCP 在 macOS 上读取、浏览和总结微信群聊消息。 |
| [`clash-verge-config`](plugins/steroids/skills/clash-verge-config/SKILL.md) | `steroids` | Clash Verge Rev / mihomo / Stash 客户端配置即代码：保留字段与 enhance 管线、Stash Override、配置不生效排查、运行态 controller 调试门槛、规则/provider/真实连接闭环、DNS 与浏览器泄漏分层验收、TUN 回环。 |
| [`skill-console`](plugins/steroids/skills/skill-console/SKILL.md) | `steroids` | 生成本地 Skill 清单控制台，审计 token 用量、description token、重复项路径、Skill 内容预览，并导出选中 Skill 的 `{name, path}` JSON。 |
| [`hippocampus`](plugins/steroids/skills/hippocampus/SKILL.md) | `steroids` | 管理 Agent 记忆与上下文：①诊断与治疗——扫描全局/项目指令、auto-memory、当前工具定义、skills 与文档，按体量/可用性/新鲜度/矛盾四维打分，生成「记忆精神科确诊书」和逐项确认的 ReviewTable；②吸收新知识——把教训路由到唯一归属并重构，而非追加笔记。内置最短充分表达、渐进披露、工具描述去噪和 auto-memory 中性原则。 |
| [`telegram-agents`](plugins/telegram/skills/telegram-agents/SKILL.md) | `telegram` | Telegram agent 配置与管理。包括 tmux 会话、Telethon 调度器、launchd 心跳定时任务。 |
| [`cdp-chrome`](plugins/chrome/skills/cdp-chrome/SKILL.md) | `chrome` | 可选的共享有头 Chrome provider。适合需要持久登录态、用户手动 CAPTCHA、反 bot 页面或 live site inspection 的环境；明确独立 CDP profile 与日常 Chrome 的验证边界。 |
| [`write-blog`](plugins/write-blog/skills/write-blog/SKILL.md) | `write-blog` | 写作全流程：从录音稿成文，或从零开始的对话式写作（选题、调研、提问漏斗、大纲迭代、初稿）。按作者 voice-dna 风格输出，附「图形为主、文字为辅」制图参考。 |

## Commands（Claude Code）

| 命令 | Plugin | 说明 |
|------|--------|------|
| [`/song <query>`](plugins/steroids/commands/song.md) | `steroids` | 搜索歌词、翻译为中文，收集趣闻和流行文化梗。 |
| [`/check-release`](plugins/telegram/commands/check-release.md) | `telegram` | 检查 Claude Code 版本更新，通过 Telegram 发送发布报告或 Anthropic 新闻简报。 |
| [`/tg-status`](plugins/telegram/commands/tg-status.md) | `telegram` | 查看所有 Telegram agent 的运行状态。 |
| [`/tg-restart <agent>`](plugins/telegram/commands/tg-restart.md) | `telegram` | 重启指定 Telegram agent 的 channel 会话。 |
| [`/tg-logs [lines]`](plugins/telegram/commands/tg-logs.md) | `telegram` | 查看心跳调度器日志。 |

## Hooks（Claude Code）

| Hook | Plugin | 说明 |
|------|--------|------|
| [`guard-payload-size`](plugins/telegram/hooks/guard-payload-size.sh) | `telegram` | 会话 payload 接近 20MB API 限制时告警，提示执行 `/compact`。临时方案，待官方修复后可移除。 |
| Telegram time awareness | `telegram` | 在 Telegram reply tool call 前注入当前本地时间，避免主动推送/回复缺少时间上下文。 |

## MCP Servers

| Server | Plugin | Runtime | 说明 |
|--------|--------|---------|------|
| `cdp-chrome` | `chrome` | Claude + Codex bundled；Hermes config-driven | Claude/Codex 通过插件本地 MCP 配置启动 launcher，读取当前用户 `cdp-chrome.port/profile_dir` 并校验监听者；Hermes 通过 `mcp_servers.cdp-chrome` 手动注册。每个 OS 用户应使用自己的端口和 profile，并运行 `doctor.sh` 验证。 |
| [`telegram-notify`](plugins/telegram/mcp-servers/telegram-notify/) | `telegram` | Claude Code only | 轻量级 Telegram 通知服务，供 agent 发送消息。 |

## Scripts

| 脚本 | 说明 |
|------|------|
| [`agent-switch`](scripts/agent-switch) | 切换本机 agent CLI 账号。当前支持 Codex：`agent-switch` 与 `agent-switch codex` 等价，显示当前 live auth 账号和账号快照列表，共享 `~/.codex` 配置、skills、sessions，仅切换账号认证快照；`agent-switch codex logout` 保存当前账号并移除 live auth，便于重新 `codex login`；切换前检查 Codex CLI、Codex.app 和 `codex-acp` 进程，`--force` 可先结束这些进程再继续。`agent-switch install` 一键 symlink 到 `~/.local/bin`。 |
| [`chrome-instances`](scripts/chrome-instances) | 管理 macOS 上的多 Chrome 实例。列出所有实例及其 Profile/窗口，按 PID 或名称聚焦窗口。通过 AppleScript 解析窗口标题，无需调试端口。`chrome-instances install` 一键 symlink 到 `~/.local/bin`。 |

## 项目结构

```
agent-steroids/
  INSTALL.md            # 唯一安装手册：给 human/agent 安装时读取
  .agents/plugins/      # Codex marketplace 配置（只列跨运行时 skill 插件）
  .claude-plugin/       # Claude marketplace 配置（列三个插件）
  steroids/              # Hermes shim：agent-steroids/steroids
  chrome/               # Hermes shim：agent-steroids/chrome
  scripts/              # 独立 CLI 工具
  plugins/
    steroids/            # 主体 skills 和通用 commands
    telegram/           # Telegram skill/commands/MCP/hooks（含 guard-payload-size）
    chrome/             # cdp-chrome provider（含 Claude/Codex MCP launcher 配置）
    write-blog/         # 写作流程 skill（Claude Code only）
  docs/
    tech/               # 技术方案和架构设计
    research/           # 调研、对比分析
```

## License

MIT
