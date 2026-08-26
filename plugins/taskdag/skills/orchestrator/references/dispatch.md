# 派发：档位 → 模型 → 命令

任务文档里只写抽象档位（`model-tier` / `effort`），本文维护档位到具体模型与 CLI 命令的映射。模型更替时只改这一份；个人机器的 provider 细节（哪家 CLI 装了、订阅哪个渠道）以使用者自己的全局记忆/配置为准，本文给公开可用的默认形态。

## model-tier 映射（2026-08 口径，过期就更新本表）

| 档位 | 适用 | 模型 |
|---|---|---|
| `high` | 强推理、高质量产出、复杂改动 | Claude Opus 5 · GPT-5.6 Sol · GLM-5.3 · DeepSeek V4-Pro（长输出：整文件重写、大批量生成） |
| `mid` | 机械、明确、量大的活 | Claude Sonnet 5 · GPT-5.6 Terra |

没有 top 档：Fable 级模型由用户在交互会话里亲自选用，不进派发映射。

## effort 映射

| taskdag | Claude Code | Codex (`model_reasoning_effort`) | 其他 |
|---|---|---|---|
| `mid` | `medium` | `medium` | 关闭/默认思考 |
| `high` | `high` | `high` | 开启思考 |
| `xhigh` | `xhigh` | `xhigh` | 最高档思考 |
| `max` | `max` | `xhigh`（封顶） | 最高档思考 |

## 命令模板

prompt 统一为一个文件（任务文件全文 + 关联 accepted ADR 全文 + 项目 CLAUDE.md 要点 + 明确的非目标与产出位置），下面记为 `prompt.md`。要求执行者：不 commit、不 push；不修改 `docs/tasks/` 与 `docs/adr/`（控制面归 orchestrator）；缺依赖只报名不联网装；产出与证据写到任务约定的位置。

**Claude Code（headless）**

```bash
claude -p "$(cat prompt.md)" --model claude-opus-5 --effort high \
  --permission-mode acceptEdits
```

**Codex**

```bash
codex exec --sandbox danger-full-access --model gpt-5.6-sol \
  -c model_reasoning_effort=high --skip-git-repo-check \
  -o result.md "$(cat prompt.md)" < /dev/null
```

`< /dev/null` 不能省，否则卡在读 stdin。后台跑用调用方 harness 的后台机制，不要在命令尾加 `&`（孤儿进程，跑完无通知）。

**OpenCode**

```bash
opencode run -m <provider>/glm-5.3 "$(cat prompt.md)"
```

`<provider>` 以本机 `opencode models` 输出为准；长输出任务换 deepseek 系。

## 并行与隔离：worktree 按 lane 开

核心不变式：**worktree 内永远串行（单写者），并行只发生在 worktree 之间**。哪些任务共用 worktree 由任务的 `lane` 字段声明（语义见 SKILL.md 与 `taskdag.py help`），派发时只执行、不重新判断：

- **有 `lane` 的任务**：worktree 名 = lane 名，首个任务开跑时创建，后续同 lane 任务复用（前一个的产出天然在场，链内零中间 merge）。`validate` 强制同 lane 至多一个任务 in_progress/review，所以 worktree 内结构上不可能并行。
- **无 `lane` 的单发任务**：临时用任务 ID 当 worktree 名，验收即收回。
- **只读/调研任务**：不开 worktree，可在仓库外跑。
- **收回时机**：lane 内任务全部终态、或到 human_checkpoint 时，review + merge 一次性收回、删 worktree；不允许跨检查点的长命 worktree。收回来只带 reviewed diff。
- **控制面不进 worktree**：`docs/tasks/`、`docs/adr/`、transition、board 只在主工作区由 orchestrator 操作；派发 prompt 须明确禁止 worker 修改 T-\*/D-\* 文件。
- 任务内部的 subagent 并行（fan-out 改不同文件）是任务自己的事，发生在同一个 worktree 里，由执行该任务的 agent 保证不冲突；lane 只管派发层。
- worktree 放在哪、用什么命令建，以使用者自己的全局配置/记忆为准；无约定时用 `git worktree add` 的默认形态。
- 如果 orchestrator 本身是带 subagent 机制的交互 agent（Claude Code 的 Agent/Workflow 等），同表映射直接用其 per-agent 的 model/effort 参数即可，不必绕道 CLI；隔离规则不变。
