# telegram-agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 合并 `setup-telegram-channel` 和 `clean-cron` 为统一的 `telegram-agents` skill，支持心跳调度和运维命令。

**Architecture:** 一个 YAML 配置定义所有 agent 和心跳。一个 launchd plist 每分钟运行 Python dispatcher，匹配 cron 表达式后通过 Telegram Bot API 发送心跳消息。三个 slash command 提供运维能力。

**Tech Stack:** Python 3 (stdlib + pyyaml), launchd, Telegram Bot API, Markdown commands

---

## File Structure

```
skills/telegram-agents/
├── SKILL.md                          # 主 Skill 文档
└── scripts/
    ├── dispatcher.py                 # 心跳调度器
    └── test-bun-proxy-stream.sh      # 保留：Bun proxy 测试脚本

commands/
├── tg-status.md                      # /tg-status 命令
├── tg-restart.md                     # /tg-restart 命令
└── tg-logs.md                        # /tg-logs 命令

# 删除
skills/setup-telegram-channel/        # 整个目录
skills/clean-cron/                    # 整个目录
```

**运行时文件布局（用户机器上，由 Skill 引导安装）：**

```
~/.config/telegram-agents/
├── agents.yaml                       # 唯一配置源
└── dispatcher.py                     # 从 Skill scripts/ 复制

~/.claude/channels/telegram-<name>/   # 每个 agent 的状态目录（.env + access.json）
~/Library/LaunchAgents/com.$USER.telegram-agents.plist
/tmp/telegram-agents.log              # dispatcher 日志
```

---

## 配置格式：agents.yaml

```yaml
agents:
  <agent-name>:
    state_dir: telegram-<name>        # 相对于 ~/.claude/channels/
    agent: <name>                     # agent 身份文件 (~/.claude/agents/<name>.md)
    tmux: channel-<name>              # tmux session 名称
    dir: ~                            # 工作目录
    heartbeats:                       # 可选，可配置多条
      - schedule: "0 7 * * *"         # 标准 5 字段 cron
        prompt: "执行某个任务"        # 纯任务描述
```

**心跳消息格式**（dispatcher 自动拼接）：`[定时任务 2026-04-07 07:00] <prompt>`

- 时间戳保证每条消息唯一，agent 不会认为是重复消息
- `[定时任务]` 前缀作为协议，agent 身份文件中应说明收到此前缀时直接执行

---

## Task 1: 创建 dispatcher.py

**Files:** Create `skills/telegram-agents/scripts/dispatcher.py`

从 clean-cron 的 `dispatch.py` 移植 cron 匹配逻辑（`_field_match` + `cron_match`），替换执行层：读取 agent state_dir 下的 `.env`（token）和 `access.json`（chat_id），通过 `urllib.request` 调 Telegram `sendMessage` API，消息自动加 `[定时任务 timestamp]` 前缀。日志写 `/tmp/telegram-agents.log`。

- [ ] 编写 dispatcher.py
- [ ] 验证 cron 匹配逻辑
- [ ] Commit

---

## Task 2: 创建 SKILL.md

**Files:** Create `skills/telegram-agents/SKILL.md`

合并两个旧 Skill 的全部知识到一份文档。参考 `skills/setup-telegram-channel/SKILL.md` 和 `skills/clean-cron/SKILL.md` 的内容。

**必须包含的章节：**
- 架构（收发分离 + Bot 隔离 + 调度解耦）
- 配置格式（agents.yaml）
- 心跳机制（消息格式、`[定时任务]` 协议、agent 身份文件中的心跳处理指令、`/compact` 用法）
- Agent 身份（文件格式、注意事项）
- 首次安装（dispatcher + launchd plist，含 `AbandonProcessGroup`、PATH、provenance 等要点）
- 添加 Agent（从 BotFather 到启动 channel session 的完整流程）
- 全局 Telegram 配置（禁用全局 plugin + send-only MCP）
- Bun Proxy 文件上传问题（workaround + 验证脚本）
- 陷阱（409 冲突、launchd 要点）

同时将 `test-bun-proxy-stream.sh` 从旧 skill 复制到新 scripts/ 目录。

- [ ] 编写 SKILL.md
- [ ] 迁移 test-bun-proxy-stream.sh
- [ ] Commit

---

## Task 3: 创建 /tg-status 命令

**Files:** Create `commands/tg-status.md`

读取 `agents.yaml` 列出所有 agent，用 `tmux has-session` 检查存活状态，从 log 提取最近心跳记录，输出汇总表格（agent / tmux 状态 / 心跳配置 / 最后心跳时间）。

- [ ] 编写 tg-status.md
- [ ] Commit

---

## Task 4: 创建 /tg-restart 命令

**Files:** Create `commands/tg-restart.md`

接受 agent 名称参数（未指定则列出供选择）。Kill 旧 tmux session → 根据 agents.yaml 配置启动新 channel session（`TELEGRAM_STATE_DIR` + `--agent` + `--channels` + `--settings`）→ 检查存活。

- [ ] 编写 tg-restart.md
- [ ] Commit

---

## Task 5: 创建 /tg-logs 命令

**Files:** Create `commands/tg-logs.md`

读取 `/tmp/telegram-agents.log` 最后 N 行（默认 30），高亮 ERROR 行。文件不存在时提示检查 launchd。

- [ ] 编写 tg-logs.md
- [ ] Commit

---

## Task 6: 删除旧 Skill

**Files:** Delete `skills/setup-telegram-channel/` 和 `skills/clean-cron/`

删除前确认迁移检查清单：架构说明、Bun proxy workaround、test script、cron 匹配逻辑、launchd 注意事项均已迁移。

- [ ] 确认迁移完整性
- [ ] 删除旧目录
- [ ] Commit

---

## Task 7: 更新 plugin.json

**Files:** Modify `.claude-plugin/plugin.json`

Minor bump：`1.3.5` → `1.4.0`

- [ ] Bump 版本号
- [ ] Commit

---

## Task 8: 迁移现有 Agent（私有，不提交）🔵

> 涉及私有配置，需用户确认后本地执行。不产生 git commit。

- [ ] 根据现有 `~/.claude/channels/` 状态目录创建 `agents.yaml`，将 clean-cron 中的三个定时任务转为心跳配置
- [ ] 安装 dispatcher 到 `~/.config/telegram-agents/`
- [ ] 更新 agent 身份文件，加入心跳处理指令
- [ ] 卸载旧 clean-cron plist，创建并加载 telegram-agents plist
- [ ] 用 `/tg-restart` 重启所有 channel session
- [ ] 端到端验证：临时心跳 → 确认日志 → 确认 agent 响应 → 删除临时心跳
- [ ] 清理旧文件（plist、`~/.config/clean-cron/`、`clean-cron-send.sh`）
