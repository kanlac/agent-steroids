---
name: tg-restart
description: 重启指定 Telegram agent 的 channel 会话
arguments:
  - name: agent-name
    description: 要重启的 agent 名称（对应 agents.yaml 中的 key）
    required: false
---

# 重启 Telegram Agent

读取 `~/.config/telegram-agents/agents.yaml` 获取所有已配置的 agent。

如果文件不存在，提示用户先完成配置。

## 确定目标 agent

用户指定的 agent 名称为："$ARGUMENTS"

- 若未指定或在 agents.yaml 中找不到，列出所有可用 agent 名称，让用户确认要重启哪一个，然后停止执行
- 若找到，继续执行重启流程

## 重启流程

所有 agent 运行在同一个 tmux session 的不同 window 中。session 名称从 agents.yaml 顶层 `tmux_session` 字段读取，window 名称 = agent key（即 agents.yaml 中的 key）。

1. **终止旧 window**：若 tmux window 存在，执行 `tmux kill-window -t <tmux_session>:<agent-name>`
2. **启动新 window**：在 session 中创建新 window：

```
tmux new-window -t <tmux_session> -n <agent-name> -c <dir> "TELEGRAM_STATE_DIR=~/.claude/channels/<state_dir> claude --channels 'plugin:telegram@claude-plugins-official' --agent <agent> --dangerously-skip-permissions --settings '{\"enabledPlugins\":{\"telegram@claude-plugins-official\":true}}'"
```

其中各字段从 agents.yaml 读取。若 tmux session 不存在，改用 `tmux new-session -d -s <tmux_session> -n <agent-name> ...` 创建。

3. **等待验证**：等待 3 秒后运行 `tmux list-windows -t <tmux_session>` 确认 window 是否存在
4. **报告结果**：告知用户重启成功或失败，失败时提示可通过 `/tg-logs` 查看日志排查
