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
├── dispatch.sh          # dispatcher，launchd 每分钟调用
└── tmux-send.sh         # 通用：创建 tmux window + 启动 Claude + 发送 prompt

~/.local/bin/            # symlink，供 launchd 调用
├── claude-cron-dispatch.sh  → dispatch.sh
└── claude-tmux-send.sh      → tmux-send.sh

~/.config/claude-cron/   # 任务目录，放 .sh 即生效
~/Library/LaunchAgents/  # 唯一的 launchd plist
```

Dispatcher 扫描任务目录，匹配 `# claude-cron:` schedule 声明后执行。所有任务共用 `claude-cron` tmux session，每个任务一个 window。

## 首次安装

检查：`launchctl list | grep claude-cron`。如果未安装：

1. Symlink 脚本到 `~/.local/bin/`（`claude-cron-dispatch.sh` → `dispatch.sh`，`claude-tmux-send.sh` → `tmux-send.sh`）
2. `mkdir -p ~/.config/claude-cron`
3. 创建 `~/Library/LaunchAgents/com.USER.claude-cron.plist`（`StartInterval` = 60，`ProgramArguments` 指向 dispatch.sh 的 symlink 路径）
4. `launchctl load` 加载

注意：plist 中路径必须是绝对路径，用 `$HOME` 的实际值替换。

## 创建任务

在 `~/.config/claude-cron/` 下创建可执行 `.sh` 文件。第二行用 `# claude-cron: <schedule>` 声明调度时间（dispatcher 靠这行匹配）：

- `daily HH:MM` — 每天固定时间
- `every Nh` — 每 N 小时（整点触发，从 0 点起算）

任务脚本调用 `~/.local/bin/claude-tmux-send.sh`，参数：`--session claude-cron --window <唯一名> --dir <工作目录> --prompt <提示词>`。

## 查看任务

- 列出任务及 schedule：`grep -r 'claude-cron:' ~/.config/claude-cron/`
- 查看运行中的 window：`tmux list-windows -t claude-cron`
- 查看日志：`cat /tmp/claude-cron.log`

## 删除/禁用

- 禁用：`chmod -x <task>.sh`
- 删除：`rm <task>.sh`，再关闭残留 window（`tmux send-keys -t claude-cron:<window> "/exit" Enter`）

## 端到端测试

新增任务后必须验证：手动执行脚本 → `tmux list-windows` 确认 window 创建 → `tmux capture-pane` 确认 Claude 收到 prompt 并开始工作 → 测试完清理 window。

## 陷阱

- **launchd PATH 极简**（仅 `/usr/bin:/bin`）：dispatcher 已补充 Homebrew 和 `~/.local/bin`，新增路径依赖需在 dispatch.sh 追加
- **Claude 启动耗时 ~20s**：大项目可能更久，必要时增加 tmux-send.sh 中的 sleep
- **window 名必须唯一**：否则 prompt 会发到别的任务里
