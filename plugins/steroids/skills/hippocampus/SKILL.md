---
name: hippocampus
description: |
  Manage everything about an agent's memory — the always-loaded instruction files (global and project CLAUDE.md / AGENTS.md) and the on-demand layer (skills, docs). Two jobs: (1) diagnose & treat — audit, score, declutter, and prune a memory environment, and (2) absorb new knowledge — turn a correction, lesson, or a "remember this" request into a durable, well-placed skill update. Use whenever the user wants to check, grade, diagnose, declutter, prune, or health-check their agent memory / CLAUDE.md / skills, asks "is my CLAUDE.md too big / any good", says memory feels bloated or the agent ignores instructions, asks where a lesson should live, or wants to record a gotcha / lesson / feedback into a skill instead of piling up raw notes. Produces a "memory health" diagnosis report (HTML) plus an interactive confirmation table (ReviewTable) before executing any change. Trigger even when the user just says "整理一下记忆 / 给我的 CLAUDE.md 打个分 / 记忆体检 / 把这个教训记进 skill" without naming the skill.
---

# Hippocampus

管理 Agent 记忆的一切——它是记忆的海马体。它握着「每一条记忆该住在哪里」的品味，用这份品味做两件事：**诊断与治疗**一个已有的记忆环境，以及**吸收新知识**、把它安放到正确的位置。

不管做哪件事，永远不要不打招呼就改写用户的记忆。诊断 → 确认 → 治疗；吸收 → 判断归属 → 重构落地。

## 哲学：每一条记忆该住在哪里

这是最重要的部分。打分、报告、吸收都是这份品味的下游；品味错了，其余只是演戏。

### 框架：预置 vs 外部

Agent 的记忆分两层，失效模式相反，这个 skill 做的每件事都挂在这个区分上。

- **预置记忆（每轮预载）**——每次对话都被载入上下文：全局 `~/.claude/CLAUDE.md`、项目 `CLAUDE.md` / `AGENTS.md`、原生 auto-memory。它是最贵的地段，因为**每一轮**都在付租金。指令文件不会被截断，但代价一样真实：越长，token 税越高、遵循度越差——指令越多，每条越容易被忽略。Claude 的 auto-memory 则有硬上限：每次只载**前 200 行或 25KB**，吃太饱的部分**直接不进上下文、完全不生效**。预置多不等于知道得多，而是遵循得更少。**预置层必须稀缺。**
- **外部记忆（按需取用）**——只在 Agent 主动取用时才被检索：skill 正文、文档、可查询的存储。它可以生长而不给每一轮交税，所以它的敌人不是大小，而是腐烂：过时、丢链接、自相矛盾。**外部层必须保持可检索、可信。**

「删掉你的记忆」和「给 Agent 一个真正的记忆」一旦区分了这两层就不再对立：预置狠狠砍，外部尽管积累——只要外部保持自律。

### 路由问题

对任何一条教训、事实或笔记，都要过一遍路由：**它该住哪里，或者根本不该留。** 别一看着有用就往记忆里塞——下面四个去处里，第一个就是「删」，很多东西的正确归属就是哪儿都不去：

- **哪儿都不去（删）**——git 历史、已合并的 PR、已完工的进度追踪、已经进了工具的东西。别处已有记录，还在记忆里留一份就是纯交税。
- **某个 skill（作为改进）**——一条只关乎某个工具或流程的教训，属于**那个 skill 内部**，在那里它每次运行都改变行为，并像代码一样被版本管理。一条 skill 专属的教训停在全局预置里就是放错了地方：给每一轮交税，却只在一个窄场景里有用。这是最常见的毛病。
- **预置（留）**——只有**同时**满足跨领域、改变决策、且在（几乎）每一轮都成立的东西：身份、用血泪学来的硬安全线、少数几条规范路径、约束 Agent 所有产出的规则。门槛极高。好的全局文件天生就短。
- **外部（留，但要诚实）**——有时才用得上、按需检索的参考知识。可以生长；但要保持有链接、不过时。

### 一条预置行的门槛

常驻层里每一行要么值这个位子，要么被砍。测试很简单：**这一行改变 Agent 下一步做什么吗？** 如果模型能从 repo 推断出来（技术栈、显而易见的约定）、如果是通用建议（「写整洁代码」）、如果含糊到无法据以行动（「注意边界情况」），它什么都没改变，只是稀释了那些真正有用的行。要砍的清单几乎总比要留的长。为信号付费，不为面积付费。

宁可一份指令文件，也不要两份互相漂移的。项目 `CLAUDE.md` 只写一行 `@AGENTS.md`（或做成它的 symlink），约定就只写一份、每个 agent 都读得到，而不是两份到周二就开始各说各话。

### 什么时候不记（克制）

- 不要为 Agent 本来就做对、或能推断出来的事加一条预置行。
- 不要为一次顺带提及建一个文档/页面——只为那些「重新推导会很痛」的知识建。
- 当一条教训确实是 skill 专属时，正确做法是改进那个 skill，而不是顺手在记忆里也留一条面包屑。两份副本会漂移。
- 一条「说不定哪天有用」的模棱两可的笔记是负债，不是资产。正是强制的稀缺，让留下来的行变得可信。

### 重构，而非追加

当一条教训确实该进某个 skill 时，好的版本会把 skill 重写得更清楚——更准的触发、一条路由规则、一个反例、一份更紧的 checklist——而不是把原始笔记钉在末尾。好的学习的衡量标准是 skill 变得**更好执行**了，而不是更长了。

### 外部层不是囤积的许可证

把召回搬进可查询的存储，并不豁免它的纪律。检索型记忆照样会过时、照样会塞满曾经有用的东西、照样值得修剪。让外部层和预置层一样诚实——区别只在于外部靠周期性清理挣得稀缺，而不是靠每轮预算。

## 路由表：要做哪件事 → 看哪个 reference

### ① 诊断与治疗

体检一个已有的记忆环境，出确诊报告，用户签字后再动手。三步永远按这个顺序：

1. **诊断**——扫描记忆环境（全局记忆、项目记忆、可触达的 skill 及 description、指令文件指向的文档；只扫**此时此地这个** Agent，不跑去扫别的项目）。自动探测存在哪些记忆文件（`CLAUDE.md` / `AGENTS.md` / auto-memory——有啥扫啥，不假设一定是 Claude）。四维打分（体量 / 可用性 / 新鲜度 / 矛盾）**按 `references/scoring-rubric.md` 的固定标准**，走三段式管线让分数跨模型/多次运行可复现：先跑 `scripts/score-mechanical.py`（机械盘点 + 各维度候选清单），再对候选做语义裁决、记入 findings 账本，所有分数由账本聚合。每扣一分都**挂证据**（`file:line` + 原文引用），生成诊断报告。
2. **确认**——交给用户一份 ReviewTable（治疗确认书），处方每项一行，由用户逐条决定改哪些、矛盾项以哪条为准。
3. **治疗**——读回用户确认后的 JSON，只执行获批的改动。

**扫描委派给 subagent 执行，主进程保持轻。** 环境很大时，扇出多个 subagent 并行取证，每个只扫**一块表面**（如各扫一个 CLAUDE.md、一批 skill、一组文档）；最后用**一个综合 pass** 做跨表面比对和最终汇总——矛盾维度天生是跨表面的（全局规则 vs 某个 skill、两个文档之间），不能纯并行，必须在汇总阶段把各 subagent 的取证合到一起再判冲突。

评分细则、等级带、报告板块与渲染 → `references/diagnosis-report.md`；确认书的交互契约、JSON schema、治疗执行 → `references/review-table.md`。

### ② 吸收新知识

把一条新知识安放进记忆。两个触发场景：**review 一段会话、提取可复用的教训**，或**用户中途主动要求记住某事**。核心动作是先跑一遍上面的**路由问题**——这条知识该住哪（预置 / 外部 / 进某个 skill / 根本不记）——再把它**重构**进目标（尤其进 skill 时，重写决策结构而非追加原始笔记）。

提炼可迁移规则、重构而非堆叠、何时不新建 reference、如何决定「不记」 → `references/absorb-knowledge.md`。

当①的一条中药是「PR 进 skill X」时，那次重写就走②的方法论。

## 备注

- 这个 skill 决定的是记忆**该住哪里**、**该不该存在**，不规定具体的 wiki/文档结构——每个仓库组织文档的方式都不一样。
- 分数是**方向性参考，不是精确度量**——报告里要说清楚。真正有价值的是处方，不是数字。
- **全程本地、不联网、不外传**：只读本机记忆文件，报告只写本地。完整报告含记忆原文（可能有私密路径/密钥），对外分享只用脱敏的「分享卡」。输出目录、跨 agent 探测、优雅失败、脱敏红线见 `references/diagnosis-report.md`。

## 致谢

- **Compound Engineering**（Every 团队）——记忆复利：把解决过的问题沉淀成可检索的文档，让下次更省。
- **Matt Van Horn**（@mvanhorn，Zimride/Lyft 创始团队、June 智能烤箱创始人，现做开源 AI 工具）——预置/外部（push/pull）记忆分层，以及「把教训 PR 进 skill 而非堆进记忆笔记」。
