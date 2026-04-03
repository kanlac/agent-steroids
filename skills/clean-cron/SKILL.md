---
name: clean-cron
description: Manage local scheduled tasks on macOS via launchd + YAML config. Use when the user wants to set up, create, list, modify, or delete recurring/timed tasks — including "设置定时任务", "新增定时任务", "每天X点执行Y", "schedule a task", "run this automatically", "set up a cron job", or any mention of recurring/periodic automated task execution. Works for any shell command, not limited to Claude Code.
---

# Clean-Cron

通用的本地定时任务调度器，基于 macOS launchd。

## 架构设计

Clean-cron 是一个**高度解耦的三层架构**：

```
┌─────────────────────────────────────────────┐
│  launchd (每分钟触发)                        │
│  ~/Library/LaunchAgents/com.USER.clean-cron  │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  dispatch.py (调度层)                        │
│  读 tasks.yaml → 匹配 cron 表达式 → 执行    │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  tasks.yaml (任务注册表)                     │
│  每个任务 = schedule + shell                 │
└─────────────────────────────────────────────┘
```

**核心原则**：调度层**完全不知道** Claude 的存在。它只做两件事——匹配时间、执行 shell。Claude agent 的启动、tmux 管理、Telegram 通知都是 shell 脚本自己的事。这意味着 clean-cron 可以调度**任何命令**——数据库备份、脚本执行、系统维护——与 crontab 等价。

## 与 Claude Code 内置调度的区别

| | Clean-Cron | Desktop Scheduled Tasks | `/loop` |
|---|---|---|---|
| 运行环境 | 终端（CLI） | Desktop App | 会话内 |
| 需要 Desktop | 否 | 是 | 否 |
| 持久化 | 是（launchd） | 是 | 否（会话级，3 天过期） |
| 访问本地文件 | 是 | 是 | 是 |
| 非 Claude 任务 | 是 | 否 | 否 |
| 最小间隔 | 1 分钟 | 1 分钟 | 1 分钟 |

**适用场景**：CLI 用户、无 Desktop App、需要调度非 Claude 任务、需要 tmux 可检查性。

## 文件布局

```
~/.config/clean-cron/
├── tasks.yaml              # 任务注册表（唯一配置源）
└── dispatch.py             # 调度器

~/.local/bin/
└── clean-cron-send.sh      # Claude 任务辅助：tmux + Telegram

~/Library/LaunchAgents/
└── com.USER.clean-cron.plist
```

## tasks.yaml 格式

```yaml
tasks:
  # 标准 cron 表达式：分 时 日 月 周
  - name: my-task
    schedule: "0 10 * * *"   # 每天 10:00
    shell: |
      echo "hello world"

  # 带随机延迟的任务（delay 单位为分钟，调度器随机取 0-N）
  - name: data-collect
    schedule: "0 10 * * *"
    delay: 180               # 随机延迟 0-180 分钟，日志会记录实际延迟
    shell: |
      ~/.local/bin/clean-cron-send.sh \
        --session clean-cron --window collect \
        --dir ~/my-project \
        --agent my-agent
```

## 首次安装

检查：`launchctl list | grep clean-cron`。如果未安装：

1. `mkdir -p ~/.config/clean-cron`
2. 复制 `${SKILL_PATH}/scripts/dispatch.py` 到 `~/.config/clean-cron/`
3. 复制 `${SKILL_PATH}/scripts/clean-cron-send.sh` 到 `~/.local/bin/`
4. 创建 `tasks.yaml`
5. 创建 plist，dispatch 通过 `cat dispatch.py | python3` 执行（绕过 provenance 限制）
6. `launchctl load` 加载

## 创建任务

往 `tasks.yaml` 的 `tasks` 列表中添加一条：

- `name`：任务标识符
- `schedule`：标准 5 字段 cron 表达式（`分 时 日 月 周`）
- `delay`：（可选）随机延迟上限，单位为分钟。调度器会随机取 `0-N` 分钟，记录到日志后再执行 shell
- `shell`：要执行的 shell 命令（支持多行）

常用 cron 表达式：

| 表达式 | 含义 |
|---|---|
| `0 9 * * *` | 每天 9:00 |
| `0 */6 * * *` | 每 6 小时 |
| `0 9 * * 1-5` | 工作日 9:00 |
| `*/30 * * * *` | 每 30 分钟 |
| `0 0 1 * *` | 每月 1 号 0:00 |

### Claude 任务的 Agent 定义

Claude 任务推荐使用 agent 定义 + `initialPrompt`，让 agent 自带任务指令：

```markdown
---
name: my-collector
description: 数据采集 agent
initialPrompt: "开始采集数据"
model: inherit
skills:
  - browser-skill
maxTurns: 200
---
你是一个数据采集 agent。按照项目中定义的采集流程执行。
```

启动时只需 `claude --agent my-collector --dangerously-skip-permissions`，`initialPrompt` 自动作为第一条消息发送。

## 查看任务

- 任务列表：`cat ~/.config/clean-cron/tasks.yaml`
- 运行中的 tmux window：`tmux list-windows -t clean-cron`
- 调度日志：`cat /tmp/clean-cron.log`

## 删除/禁用任务

从 `tasks.yaml` 中删除或注释对应条目即可。

## 清理历史 window

- 列出：`tmux list-windows -t clean-cron`
- 关闭单个：`tmux kill-window -t clean-cron:<name>`
- 关闭全部：`tmux kill-session -t clean-cron`

## 端到端测试

新增任务后验证：临时设置一个即将到来的 schedule → 等待触发 → 确认日志出现 "running" → 确认 shell 执行成功 → 删除测试任务。

## 陷阱

- **`AbandonProcessGroup` 必须为 true**：launchd 默认在主进程退出后杀掉整个进程组。dispatcher 后台化任务后退出，若缺少此键，后台任务会被立即终止
- **macOS provenance 限制**：Claude Code 创建的文件带 `com.apple.provenance`，launchd 无法直接执行。解决方案：dispatch.py 通过 `cat | python3` 管道执行，task shell 通过 `echo | bash` 执行
- **launchd PATH 极简**（仅 `/usr/bin:/bin`）：plist 中必须显式补充 Homebrew 和 `~/.local/bin`
- **依赖 pyyaml**：dispatch.py 使用 Python `yaml` 模块解析 tasks.yaml，需确保 `pip3 install pyyaml`
- **Telegram 通知可选**：依赖 `~/.claude/channels/telegram/.env` 中的 `TELEGRAM_BOT_TOKEN` 和 `access.json` 中的 `allowFrom`。未配置则静默跳过
