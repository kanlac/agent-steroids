---
name: tg-status
description: 查看所有 Telegram agent 的运行状态
---

# Telegram Agent 状态总览

读取 `~/.config/telegram-agents/agents.yaml` 获取所有已配置的 agent 列表。

如果该文件不存在，告知用户先配置，并参考 telegram-agents skill。

## 数据收集

对每个 agent：

1. **tmux 状态**：运行 `tmux list-windows -t <tmux_session>` 检查对应 window（名称 = agent key）是否存在
2. **最近心跳**：读取 `/tmp/telegram-agents.log` 最后 20 行，提取该 agent 名称对应的最近一条心跳记录和时间戳
3. **心跳计划**：从 agents.yaml 中读取该 agent 的 `heartbeats[].schedule` 列表

## 输出格式

以表格形式输出摘要：

| Agent | tmux 状态 | 心跳计划 | 最近心跳时间 |
|-------|-----------|----------|--------------|
| sage  | ✅ alive  | 0 7 * * * | 2026-04-07 07:00 |
| ...   | ...       | ...      | ...          |

- tmux 存活用 ✅，未运行用 ❌
- 心跳计划多个时换行显示
- 若日志中找不到该 agent 的心跳记录，显示「无记录」
- 若 `/tmp/telegram-agents.log` 不存在，心跳列全部显示「日志不存在」
