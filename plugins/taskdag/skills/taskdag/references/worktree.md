# 并行与隔离：worktree 按 lane 开

怎么选模型、怎么定推理强度、各 CLI 怎么调用，都不在这里，以 dispatch skill 为准（能力依赖：任意具备派发能力的 agent 或 skill 均可）。本文只讲 lane 到隔离环境的映射。

核心不变式：**worktree 内永远串行（单写者），并行只发生在 worktree 之间**。哪些任务共用 worktree 由任务的 `lane` 字段声明（语义见 SKILL.md 与 `taskdag.py help`），派发时只执行、不重新判断：

- **有 `lane` 的任务**：worktree 名 = lane 名，首个任务开跑时创建，后续同 lane 任务复用（前一个的产出天然在场，链内零中间 merge）。`validate` 强制同 lane 至多一个任务 in_progress/review，所以 worktree 内结构上不可能并行。
- **无 `lane` 的单发任务**：临时用任务 ID 当 worktree 名，验收即收回。
- **只读/调研任务**：不开 worktree，可在仓库外跑。
- **收回时机**：lane 内任务全部终态、或到 human_checkpoint 时，review + merge 一次性收回、删 worktree；不允许跨检查点的长命 worktree。收回来只带 reviewed diff。
- **控制面不进 worktree**：`docs/tasks/`、`docs/adr/`、transition、board 只在主工作区操作；派发 prompt 须明确禁止 worker 修改 T-\*/D-\* 文件。
- 任务内部的 subagent 并行（fan-out 改不同文件）是任务自己的事，发生在同一个 worktree 里，由执行该任务的 agent 保证不冲突；lane 只管派发层。
- worktree 放在哪、用什么命令建，以使用者自己的全局配置/记忆为准；无约定时用 `git worktree add` 的默认形态。
