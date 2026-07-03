---
name: memory-clinic
description: |
  Audit, score, and clean up an agent's memory environment — the always-loaded instruction files (global and project CLAUDE.md / AGENTS.md) and the on-demand layer (skills, docs). Use whenever the user wants to check, grade, diagnose, declutter, prune, or health-check their agent memory / CLAUDE.md / skills, asks "is my CLAUDE.md too big / any good", says memory feels bloated or the agent ignores instructions, or asks where a lesson should live. Produces a "memory health" diagnosis report (HTML) plus an interactive confirmation table (ReviewTable) that captures which fixes to apply before the agent executes them. Trigger this even when the user just says "整理一下记忆 / 给我的 CLAUDE.md 打个分 / 记忆体检" without naming the skill.
---

# Memory Clinic

给 Agent 记忆做的诊所。它握着「每一条记忆该住在哪里」的品味，把品味变成一份**可打分的诊断**，再用一份**人工确认**收尾。

诊断 → 确认 → 治疗。永远不要不打招呼就改写用户的记忆。

## 一个核心：预置 vs 外部

Agent 的记忆分两层，失效模式相反，这个 skill 做的每件事都挂在这个区分上。

- **预置记忆（每轮预载）**——每次对话都被载入上下文：全局 `~/.claude/CLAUDE.md`、项目 `CLAUDE.md` / `AGENTS.md`、原生 auto-memory。失效模式是**膨胀**：每一行都在给每一轮交税，超过预算后 harness 会静默截断，于是 Agent 反而更笨，不是更聪明。预置层必须稀缺。
- **外部记忆（按需取用）**——只在需要时被检索：skill 正文、文档。它可以生长，但会**腐烂、失联、自相矛盾**。外部层必须保持可检索、可信。

任何一条教训的路由问题就是：*它属于预置、属于外部、属于某个 skill（作为改进）、还是根本不该留（git 里已经有了）？* 完整品味见 `references/memory-philosophy.md`——在对「留什么、移什么、删什么」下判断之前先读它。

## 诊所做什么

三件事，永远按这个顺序：

1. **诊断** —— 扫描记忆环境、打分、生成诊断报告。
2. **确认** —— 交给用户一份 ReviewTable（治疗确认书），由用户逐条决定到底改哪些。
3. **治疗** —— 读取用户确认后的结果，只执行获批的改动。

### 扫描范围

读当前环境能读到的一切：

- 全局记忆：`~/.claude/CLAUDE.md`（以及存在的话 `~/.claude/AGENTS.md`）
- 项目记忆：仓库根目录的 `CLAUDE.md` / `AGENTS.md`
- 可触达的外部层：已安装/项目内的 skill 及其 description，以及指令文件指向的文档

不要跑去扫别的项目的记忆。扫的是**此时此地这个** Agent。

## 四个诊断维度

每个维度回答一个不同的问题，且必须**挂证据**——每扣一分都要指向具体的 `file:line` 并引用原文。没有证据就不扣分；没有证据支撑的分数看起来像套模板，没人会信。

| 维度 | 它问的 | 典型信号 |
|---|---|---|
| **① 体量 Bloat** | 太臃肿吗？ | 单文件 >200 行、总大小、每轮 token 税、大到被静默截断 |
| **② 可用性 Usability** | 有用且说得清吗？ | 不改变任何决策的通用废话、模型能从 repo 推断的内容、含糊到无法执行的指令 |
| **③ 新鲜度 Freshness** | 过时了吗？ | 指向已删/改名文件的断链、已完工的进度记录、失效的时效声明 |
| **④ 矛盾 Contradiction** | 自相打架吗？ | 跨预置/外部：全局规则与某个 skill、两个文档之间的冲突（成对呈现，带行号） |

分数先按表面聚合（全局记忆 / 项目记忆 / 技能 / 文档），再合成预置分与外部分（**5:5** 加权），最后得到 0–100 的总分和一个等级带。这个分数是**方向性参考，不是精确度量**——报告里要说清楚。评分细则、等级带、报告生成见 `references/diagnosis-report.md`。

## 处方：两类修复，带把握程度

清理动作分两类，这个区分正是「确认」这一步存在的意义：

- **💊 西药（机械、高把握）**——确定性的、可直接执行的修复：删掉 git 已有的完工记录、拆分一个 260 行的文件、把项目文件收敛为 `@AGENTS.md`。
- **🌿 中药（判断、中/低把握）**——需要人看一眼的语义决定：两条冲突指令以哪条为准、某条教训是否该 PR 进某个 skill、某个"临时"标记是否真的失效了。这类给出建议和理由，由用户定夺，而不是替他拍板。

## 先确认再治疗（ReviewTable）

诊断不等于许可。报告之后，交给用户一份可交互的**治疗确认书**（ReviewTable）：处方每项一行，列出病灶、证据、建议动作和把握程度；用户勾选要执行哪些，矛盾项则写下以哪条为准。保存时落一份 JSON 到磁盘，Agent 读回来，只执行获批的改动。这就是诊所永远不会不打招呼改写记忆的原因。交互契约、JSON schema、模板见 `references/review-table.md`。

## 工作流程

1. 读 `references/memory-philosophy.md` 拿到路由品味，再扫上面的范围。
2. 按 `references/diagnosis-report.md` 给四维打分并挂证据；用 `assets/diagnosis-template.html` 渲染诊断报告。
3. 按 `references/review-table.md` 用 `assets/review-table-template.html` 生成治疗确认书，指引用户去填。
4. 用户说填好了之后，读确认 JSON，只执行获批的项——西药直接执行，中药按用户的决定执行。
5. 复述最终的健康变化（分数会变成多少），让这个循环落在一个看得见的改善上。

## 备注

- 这个 skill 决定的是记忆**该住哪里**、**该不该存在**，它不规定具体的 wiki/文档结构——每个仓库组织文档的方式都不一样。
- 相关：`meta-learning` 负责把一条教训**重写进** skill 的更深功夫（重构，而非追加）。当一条中药是「PR 进 skill X」时，那属于 `meta-learning` 的活。
