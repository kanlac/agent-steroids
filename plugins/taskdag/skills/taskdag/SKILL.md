---
name: taskdag
description: Repo-native ADR + Task DAG data plane. Use when a repository should adopt or operate structured task and decision docs - initializing docs/tasks and docs/adr with the vendored taskdag.py, migrating a legacy task list into the DAG, creating tasks and their dependency/lane fields, querying which tasks are runnable next, transitioning task lifecycle and recording acceptance evidence, recording or superseding ADRs, or regenerating the TASK-DAG.html board. Model and effort selection, prompt composition and CLI invocation are out of scope - they belong to the dispatch capability. Triggers - task DAG, ADR, task board, 任务板, 任务 DAG, 下一个任务, 架构决策, human checkpoint, taskdag.
---

# taskdag — 任务 DAG 与 ADR 的数据面

这套系统把项目的「要做什么」和「为什么这么定」收进两类结构化文档，取代散落的状态板和口径描述：

- **Task**（`docs/tasks/T-*.md`）：带依赖的任务节点，frontmatter 是状态与关系的唯一事实源。
- **ADR**（`docs/adr/D-*.md`）：约束后续实现的决策记录，只能被 supersede，不能静默改。

分层职责：**事实**在项目文档里；**确定性行为**（校验、查询、状态机、看板生成）在 vendor 进项目的 `scripts/taskdag.py` 里；**用法**（怎么初始化、怎么标字段、怎么选下一个、怎么收口）在本 skill 里。任何 runtime 的 agent 打开仓库都能靠 `python3 scripts/taskdag.py help` 独立操作，不依赖本 skill 存在。

**边界**：本 skill 不管派发——选模型、定推理强度、拼 prompt、调 CLI 一律交给 dispatch 能力（dispatch skill 或等价物），本 skill 只提供任务事实与交接约定。

## 初始化与迁移

把本 skill 目录下 `scripts/taskdag.py` 复制到项目 `scripts/`，建 `docs/tasks/`、`docs/adr/`，写一份简短的 `docs/tasks/AGENTS.md`（并建 `CLAUDE.md` symlink）。完整步骤、AGENTS.md 模板、旧任务清单迁移法（含编号下限 `NUMBER_FLOOR`、归档横幅写法）见 `references/init.md`。

项目约定有偏差时改脚本顶部常量区，不改逻辑；脚本升级 = 用本 skill 的新副本覆盖项目副本（对比顶部 `VERSION`），重跑 `validate` 和 `board`。

## 任务字段

**任务 ≠ 目标**：任务是可执行、可验收的动作；目标是结果指标（「本周真实生成 ≥ N 次」「排名进前十」），**不建任务**——目标放专门的目标文档，相关任务用 `source` 指向它，看板用脚本的 `BOARD_NOTE` 常量把当前目标钉在头部。持续职责可作为长期 in_progress 任务；acceptance-only 的人工检查点（过一遍就绪清单）是合法任务，因为「过清单」本身可执行。

每个任务标 `priority: p0 | p1 | p2`——p0 = 当前周期必经（本周目标的动作与前置、外部时钟正在走的长周期项）；p1 = 下一里程碑/发布窗口前必须就绪；p2 = 机会性，晚做代价小。优先级随周期推进要维护，不是设完不管。

任务不标模型和推理强度：派发时由派发方按任务正文判断，任务文件里写死只会和实际可用的模型脱节。旧文档里遗留的 `model-tier` / `effort` 字段脚本会忽略。

任务还可标 `lane`（可选，人类任务也可标）：**写入面互斥的串行泳道**。依赖边表达顺序约束，lane 表达资源互斥，两者正交（有依赖不一定写同一片文件，写同一片文件的不一定有依赖）。规划时判断：这个任务会不会和另一个未完成任务写同一片文件？会，就标同一个 lane——这声明它们必须串行、共用一个 worktree；不同 lane / 无 lane 即声明写入面不重叠、可并行。lane 名用小写 slug（可作分支/目录名），`validate` 强制同 lane 内同时至多一个任务 in_progress/review（单写者）。

lane 到 worktree 的开设与收回见 `references/worktree.md`。

## 日常驱动循环

1. `python3 scripts/taskdag.py validate` — 先保证仓库合法。
2. `query type=task status=in_progress`、`status=review`、`status=blocked` — 先收口在途的，再开新的。
3. `query type=task runnable=true` — 得到可开跑集合。**runnable ≠ 该跑**：lane 被占的先排队（query 输出标 `lane:…(busy)`）；再按 `priority`（p0 在前），同级内比——通往下一个人工检查点的最短路径 > 解锁的下游数量 > 证据可独立拿到。
4. 派发交给 dispatch 能力，本 skill 只给交接约定：worker 不改 `docs/tasks/`、`docs/adr/`，不 commit；产出与证据落在任务约定的位置；同 lane 的任务共用一个隔离环境（见 `references/worktree.md`）。
5. 验收：对照任务的「验收与证据」拿一手证据，不信执行者自报。
6. `transition <id> <status> --reason "…"` — 状态只走脚本；证据摘要写进 `--reason`（脚本会追加到执行记录，最新在上）。
7. `board` — 重新生成看板（输出路径是脚本 `BOARD_FILE` 常量，可指向仓库外的发布目录）。看板是只读视图，不是编辑入口。

## 生命周期纪律

- **不手改 `status`**，一律 `transition`（状态机会拦非法迁移，终态自动摘除检查点指针）。
- `blocked` 只用于**外部条件或缺决策**（等一个日期、等一个账号、等用户拍板）。普通"依赖没完成"就是 planned 未 runnable，不算 blocked。blocked 任务的「启动条件」必须写清具体缺什么。
- `manual_acceptance` 判定：可重复测试、数据、日志、截图能客观判定 → `none`；需要负责人的主观判断或权限（体验质量、合规、花钱、发布授权）→ `required`，且「人工验收」小节恰好一条最小动作 + 一条通过标准。环境、凭据、账号属于**启动条件**，不因为"要人给"就算人工验收。
- `human_checkpoint: next` 全仓最多一个，标当前批次冲刺的里程碑；它关闭后先选定下一个再开新批次。
- **控制面只在主工作区改**：`docs/tasks/`、`docs/adr/`、transition、board 一律在主工作区操作；worker worktree 只干活，不碰 T-\*/D-\* 文件（否则 merge 回来会出现两个状态事实源）。worker 的证据写到任务约定的产出位置，验收后由维护任务板的一方用 `transition --reason` 记录。

## ADR 治理

- 收录边界：**约束后续实现的产品/系统/口径决策**进 ADR；派发方法、review 时机这类元工作流规则不进 ADR。
- 小澄清直接更新原 ADR；改变核心取舍开新编号，双方用 `supersedes` / `superseded_by` 互链（脚本强制互相声明），旧的标 `superseded`。不删除、不静默改。
- 任务用 `related_adrs` 指向约束它的决策；实现与 accepted ADR 冲突时，赢的是 ADR——要么改实现，要么先 supersede 决策。
