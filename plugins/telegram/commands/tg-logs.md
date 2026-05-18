---
name: tg-logs
description: 查看 Telegram agent 心跳调度器日志
arguments:
  - name: lines
    description: 显示最后 N 行日志（默认 30）
    required: false
---

# Telegram Agent 日志

查看心跳调度器的运行日志 `/tmp/telegram-agents.log`。

显示行数由用户指定："$ARGUMENTS"。若未指定，默认显示最后 30 行。

## 读取日志

若 `/tmp/telegram-agents.log` 不存在，提示用户检查调度服务是否在运行：

```
launchctl list | grep telegram-agents
```

并建议参考 telegram-agents skill 重新配置调度任务。

## 输出

读取日志文件的最后 N 行并输出。输出时：

- 包含 `ERROR` 的行用醒目方式标注（如加粗或在行首加 ⚠️）
- 保留原始日志格式，不做其他处理
