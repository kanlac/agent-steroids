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

1. **终止旧会话**：若 tmux 会话存在，执行 `tmux kill-session -t <tmux>`
2. **启动新会话**：组装启动命令并用 tmux 包裹运行：

```
tmux new-session -d -s <tmux> "TELEGRAM_STATE_DIR=~/.claude/channels/<state_dir> claude --channels 'plugin:telegram@claude-plugins-official' --agent <agent> --dangerously-skip-permissions --settings '{\"enabledPlugins\":{\"telegram@claude-plugins-official\":true}}'"
```

其中 `<tmux>`、`<state_dir>`、`<agent>` 均从 agents.yaml 对应 agent 配置中读取。

3. **等待验证**：等待 3 秒后运行 `tmux has-session -t <tmux>` 确认会话是否成功启动
4. **报告结果**：告知用户重启成功或失败，失败时提示可通过 `/tg-logs` 查看日志排查
