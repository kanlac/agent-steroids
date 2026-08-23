---
name: orchestrator
description: Repo-native ADR + Task DAG control plane. Use when a repository should adopt or operate structured task and decision docs - initializing docs/tasks and docs/adr with the vendored taskdag.py, migrating a legacy task list into the DAG, choosing what to run next, creating or splitting tasks at one-dispatch granularity with model-tier/effort annotations, dispatching tasks to any agent CLI (Claude Code, Codex, OpenCode), transitioning task lifecycle, recording or superseding ADRs, or regenerating the TASK-DAG.html board. Triggers - task DAG, ADR, task board, 任务板, 任务 DAG, 派活, 下一个任务, 架构决策, human checkpoint, taskdag.
---

# taskdag orchestrator — 任务 DAG 与 ADR 的控制面

这套系统把项目的「要做什么」和「为什么这么定」收进两类结构化文档，取代散落的状态板和口径描述：

- **Task**（`docs/tasks/T-*.md`）：带依赖的任务节点，frontmatter 是状态与关系的唯一事实源。
- **ADR**（`docs/adr/D-*.md`）：约束后续实现的决策记录，只能被 supersede，不能静默改。

分层职责：**事实**在项目文档里；**确定性行为**（校验、查询、状态机、看板生成）在 vendor 进项目的 `scripts/taskdag.py` 里；**方法**（怎么拆、怎么选、怎么派、怎么收）在本 skill 里。任何 runtime 的 agent 打开仓库都能靠 `python3 scripts/taskdag.py help` 独立操作，不依赖本 skill 存在。

## 初始化与迁移

把本 skill 目录下 `scripts/taskdag.py` 复制到项目 `scripts/`，建 `docs/tasks/`、`docs/adr/`，写一份简短的 `docs/tasks/AGENTS.md`（并建 `CLAUDE.md` symlink）。完整步骤、AGENTS.md 模板、旧任务清单迁移法（含编号下限 `NUMBER_FLOOR`、归档横幅写法）见 `references/init.md`。

项目约定有偏差时改脚本顶部常量区，不改逻辑；脚本升级 = 用本 skill 的新副本覆盖项目副本（对比顶部 `VERSION`），重跑 `validate` 和 `board`。

## 拆分粒度：一个任务 = 一次派发

判断标准：**这件事能不能交给一个 agent 在一个上下文窗口里做完，并且验收可以独立判定**。能，就是一个任务 ID，哪怕它内部含几件小事；不能，就拆成多个任务、用 `depends_on` 连起来。不按"概念上是不是一件事"拆，按派发单位拆。

**任务 ≠ 目标**：任务是可执行、可验收的动作；目标是结果指标（「本周真实生成 ≥ N 次」「排名进前十」），**不建任务**——目标放专门的目标文档，相关任务用 `source` 指向它，看板用脚本的 `BOARD_NOTE` 常量把当前目标钉在头部。持续职责可作为长期 in_progress 任务；acceptance-only 的人工检查点（过一遍就绪清单）是合法任务，因为「过清单」本身可执行。

每个任务标 `priority: p0 | p1 | p2`——p0 = 当前周期必经（本周目标的动作与前置、外部时钟正在走的长周期项）；p1 = 下一里程碑/发布窗口前必须就绪；p2 = 机会性，晚做代价小。优先级随周期推进要维护，不是设完不管。

agent 任务在规划时另标两个字段（人类任务不标）：

- `model-tier: high | mid` — 抽象档位，**不写具体模型名**（模型常换，映射表只维护一处）。high = 需要强推理/高质量产出；mid = 机械、明确、量大的活。没有 top 档：顶级模型只由用户在交互中亲自选用，凡是委派出去的任务都用不到。
- `effort: mid | high | xhigh | max` — 推理努力档位，派发时映射到各家 CLI 的对应参数。

档位到具体模型与命令的映射见 `references/dispatch.md`。

## 日常驱动循环

1. `python3 scripts/taskdag.py validate` — 先保证仓库合法。
2. `query type=task status=in_progress`、`status=review`、`status=blocked` — 先收口在途的，再开新的。
3. `query type=task runnable=true` — 得到可开跑集合。**runnable ≠ 该跑**：先按 `priority`（p0 在前），同级内再比——通往下一个人工检查点的最短路径 > 解锁的下游数量 > 证据可独立拿到 > 写入面不重叠（重叠的不并行）。
4. 派发（见 `references/dispatch.md`）：prompt = 任务文件全文 + 关联的 accepted ADR + 项目 CLAUDE.md 要点；要求执行者不 commit、产出落在任务约定的位置；并行任务各开独立 worktree。
5. 验收：对照任务的「验收与证据」拿一手证据，不信执行者自报。
6. `transition <id> <status> --reason "…"` — 状态只走脚本；证据摘要写进 `--reason`（脚本会追加到执行记录，最新在上）。
7. `board` — 重新生成看板（输出路径是脚本 `BOARD_FILE` 常量，可指向仓库外的发布目录）。看板是只读视图，不是编辑入口。

## 生命周期纪律

- **不手改 `status`**，一律 `transition`（状态机会拦非法迁移，终态自动摘除检查点指针）。
- `blocked` 只用于**外部条件或缺决策**（等一个日期、等一个账号、等用户拍板）。普通"依赖没完成"就是 planned 未 runnable，不算 blocked。blocked 任务的「启动条件」必须写清具体缺什么。
- `manual_acceptance` 判定：可重复测试、数据、日志、截图能客观判定 → `none`；需要负责人的主观判断或权限（体验质量、合规、花钱、发布授权）→ `required`，且「人工验收」小节恰好一条最小动作 + 一条通过标准。环境、凭据、账号属于**启动条件**，不因为"要人给"就算人工验收。
- `human_checkpoint: next` 全仓最多一个，标当前批次冲刺的里程碑；它关闭后先选定下一个再开新批次。

## ADR 治理

- 收录边界：**约束后续实现的产品/系统/口径决策**进 ADR；调度方法、review 时机这类元工作流规则不进 ADR（它们属于本 skill）。
- 小澄清直接更新原 ADR；改变核心取舍开新编号，双方用 `supersedes` / `superseded_by` 互链（脚本强制互相声明），旧的标 `superseded`。不删除、不静默改。
- 任务用 `related_adrs` 指向约束它的决策；实现与 accepted ADR 冲突时，赢的是 ADR——要么改实现，要么先 supersede 决策。

## 提交前复审

日常小改不派独立 reviewer。用户明确要求 review 或准备 commit 时：实现与确定性检查全部做完，再做**一次**独立的唱反调复审，优先跨模型（Claude 实现→Codex 评，反之亦然）；给 reviewer 原始材料（任务文档、ADR、diff、证据），不给暗示性结论，明确禁止其修改。评完逐条自行复现再采纳（跨模型输出是证据不是权威），拒绝要写具体理由，不开连环 review。复审结论、修复项、拒绝项及理由，用 `transition --reason` 或直接补进任务「执行记录」，留下可追溯证据。
