---
name: claude-cron
description: Manage scheduled tasks for Claude Code on macOS (launchd + tmux). Use when the user wants to set up, create, list, modify, or delete recurring/timed tasks — including "设置定时任务", "新增定时任务", "每天X点执行Y", "schedule a task", "run this automatically", "set up a cron job for Claude", or any mention of recurring/periodic automated Claude Code execution.
---

# Claude Cron

定时向 tmux 中无人值守的 Claude Code 发送 prompt。

## 与 `/loop` 的区别

Claude Code 自带 `/loop` 命令可以在会话内定时重复执行 prompt，但它是**会话级**的——关闭终端就没了，最长 3 天自动过期。适合临时轮询（"5 分钟后再看一下这个部署"）。

claude-cron 适合**持久的、无人值守的定时任务**：每天固定时间采集数据、定期检查更新等。任务脚本写在磁盘上，重启不丢失，launchd 负责调度。

## 为什么这么设计

- **launchd**：macOS 原生调度器（crontab 已 deprecated），支持唤醒后补执行
- **单 dispatcher + 任务目录**：一次注册 launchd，之后新增任务只需往 `~/.config/claude-cron/` 放脚本
- **tmux**：Claude Code 需要持久交互终端，tmux 命名 window 断开后仍存活，方便事后查看

## 架构

```
${SKILL_PATH}/scripts/
└── tmux-send.sh         # 通用：创建 tmux window + 启动 Claude + 发送 prompt

~/.local/bin/
└── claude-tmux-send.sh  # tmux-send.sh 的副本

~/.config/claude-cron/   # 任务目录，放 .sh 即生效
~/Library/LaunchAgents/  # plist（dispatch 逻辑内联其中）
```

Dispatch 逻辑**内联在 plist 中**（不依赖外部脚本文件），扫描任务目录，匹配 `# claude-cron:` schedule 声明后通过 `cat | bash` 执行任务脚本。所有任务共用 `claude-cron` tmux session，每次执行创建新 window（名称含时间戳，如 `check-release-260324-1000`），不复用之前的 session。旧 window 不自动清理，由用户手动管理。

如果检测到 Telegram bot token（`~/.claude/channels/telegram/.env`），任务启动时会通过 Telegram Bot API 发送通知（纯 HTTP 调用，不依赖 MCP，多进程不冲突）。

## 首次安装

检查：`launchctl list | grep claude-cron`。如果未安装：

1. 复制 `tmux-send.sh` 到 `~/.local/bin/claude-tmux-send.sh`
2. `mkdir -p ~/.config/claude-cron`
3. 创建 `~/Library/LaunchAgents/com.USER.claude-cron.plist`，dispatch 逻辑内联在 `ProgramArguments` 的 `bash -c` 中（参考现有 plist）
4. `launchctl load` 加载

注意：plist 中路径必须是绝对路径，用 `$HOME` 的实际值替换。

## 创建任务

在 `~/.config/claude-cron/` 下创建可执行 `.sh` 文件。第二行用 `# claude-cron: <schedule>` 声明调度时间（dispatcher 靠这行匹配）：

- `daily HH:MM` — 每天固定时间
- `every Nh` — 每 N 小时（整点触发，从 0 点起算）

任务脚本通过 `cat | bash -s` 调用 tmux-send（绕过 provenance 限制）：

```bash
/bin/cat ~/.local/bin/claude-tmux-send.sh | /bin/bash -s -- \
  --session claude-cron --window <名称> --dir <工作目录> --prompt <提示词>
```

## 查看任务

- 列出任务及 schedule：`grep -r 'claude-cron:' ~/.config/claude-cron/`
- 查看运行中的 window：`tmux list-windows -t claude-cron`
- 查看日志：`cat /tmp/claude-cron.log`

## 删除/禁用

- 禁用：`chmod -x <task>.sh`
- 删除：`rm <task>.sh`

## 清理历史 window

每次执行都会创建新 window，旧 window 不自动清理。手动管理：

- 列出所有 window：`tmux list-windows -t claude-cron`
- 关闭单个：`tmux kill-window -t claude-cron:<window-name>`
- 关闭全部：`tmux kill-session -t claude-cron`

## 端到端测试

新增任务后必须验证：手动执行脚本 → `tmux list-windows` 确认 window 创建 → `tmux capture-pane` 确认 Claude 收到 prompt 并开始工作 → 测试完清理 window。

## 陷阱

- **`AbandonProcessGroup` 必须为 true**：launchd 默认在主进程退出后杀掉整个进程组。dispatcher 用 `&` 后台化任务，主脚本立即退出，若缺少此键，后台任务会被 launchd 立即终止。plist 中必须包含 `<key>AbandonProcessGroup</key><true/>`
- **macOS provenance 限制**：Claude Code 创建的文件带 `com.apple.provenance` 属性，launchd 无法直接执行。解决方案：dispatch 逻辑内联在 plist 中，task 脚本通过 `cat | bash` 管道执行（`cat` 可以读 provenance 文件，只是不能 exec）
- **launchd PATH 极简**（仅 `/usr/bin:/bin`）：内联 dispatch 已补充 Homebrew 和 `~/.local/bin`，新增路径依赖需在 plist 的 bash -c 中追加
- **Claude 启动耗时 ~20s**：大项目可能更久，必要时增加 tmux-send.sh 中的 sleep
- **window 名自动带时间戳**：`tmux-send.sh` 自动在 window 名后追加 `-YYMMDD-HHMM`，无需手动保证唯一
- **Telegram 通知可选**：依赖 `~/.claude/channels/telegram/.env` 中的 `TELEGRAM_BOT_TOKEN` 和 `access.json` 中的 `allowFrom`。未配置则静默跳过
