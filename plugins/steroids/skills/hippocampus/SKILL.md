---
name: hippocampus
description: Taste rules for what belongs in an agent's context (CLAUDE.md/AGENTS.md, auto-memory, skill descriptions and bodies, tool descriptions). Use when auditing or trimming them, or when asked to remember a lesson or improve a skill.
---

# Hippocampus

管理 Agent 的记忆与上下文。产出不是报告，是一份对照下面编号的问题清单：每条带 `路径:行号`、原文和改法。两种用法：

- **体检**：用户要清理 CLAUDE.md / AGENTS.md、auto-memory、skill 或工具描述时，逐条对照品味，列清单；批量删改前把清单给用户过目，点头后再动。
- **吸收**：用户说「记住 / 沉淀 / 改 skill」，请求本身就是授权。按 T10 找主人，重构落地，汇报一句结果，不出清单。

上下文分两类：**预置**（全局/项目指令、auto-memory、提前加载的工具描述，每轮都交税，必须稀缺）和**外部**（skill、reference、文档、延迟加载工具，按需取用，可以丰富但要可检索、不过时、不冲突）。

## 品味清单

**T1 最短充分表达。** 一行够就不写一段，一段够就不建一篇；每多一句都必须改变 Agent 的判断或动作。
- 反：「请务必注意，在任何情况下都要认真对待……」，一句「必须 X」即可。
- 反：一条规则配三个例子；例子只用于消除真实歧义。

**T2 只教模型不知道的。** 能从代码、目录、schema 或上下文推断的不写；通用建议不写。
- 反：「本项目用 TypeScript + React」「`src/` 放源码」，`package.json` 和目录本身就是答案。
- 反：「写整洁代码」「注意性能」「合理处理边界情况」，没有任何一句改变下一步动作。

**T3 护栏越少越好。** 为旧模型的毛病加的护栏，在新模型上是累赘：多烧上下文、拖慢工作，还会让模型在你希望它继续的地方停下。写意图与边界，把安全的流程明确放权，把完成标准写进任务。
- 反：「每次改代码前先读 `docs/ARCHITECTURE.md` 和整个 `src/`」，改个拼写也要通读全仓。
- 反：「改完一定记得跑测试」，模型自己会跑，这条只会引来多余的测试。
- 反：「任何改动都先问我」「做完第一版停下来等我审核」「不要自作主张」，这些让模型提前停工。
- 反：「严格按以下 8 步执行」，除非流程脆弱到必须锁死顺序。
- 正：「本地测试用一次性 fixture、无生产访问。跑测试、修因本次改动引起的失败、重跑受影响的测试，不用逐步征求同意。」

**T4 把判断还给模型。** 除高风险红线、非显然约束和脆弱流程外，不堆规则、步骤和 recipe。判定：删掉这条，模型会做错吗？不会就删。
- 反：一份 code review skill 写成 12 步 checklist，每步还附模板句。
- 正：「删历史文件用 `git rm` + `.gitignore`，不重写历史」，这是非显然约束，留。

**T5 一个事实一个主人。** 工具规则住工具描述或对应 skill，项目规则住项目记忆，同一事实不在多处出现。
- 反：同一条规则在全局 CLAUDE.md、项目 CLAUDE.md 和某个 skill 里各有一份，措辞还略有不同。
- 反：auto-memory 里记了一遍 skill 正文已经写明的东西。

**T6 常驻层只留路由和硬约束。** 全局/项目指令是路由器，「凡 X 场景先用 skill Y」是它的正当职责；教训本体（步骤、参数表、命令序列、转义表）住对应 skill。判定：把这段删掉，对应 skill 能原样恢复这份能力吗？能就是住错了。
- 反：全局 CLAUDE.md 里内联某个 CLI 的完整参数表和三种失败排查步骤。
- 正：「处理飞书任务先 `lark-cli skills read <name>`，别凭记忆调命令」，一行指针，够了。

**T7 Skill description 只回答「什么时候用」。** 每条 description 都常驻上下文，装太多时运行时会截短它，模型看到的更少、选得更差。写触发条件，一两句话，不讲内部流程、不堆触发词、不抢戏。
- 反：「Use for any database-related task」，会让模型一碰数据库就加载它；应是「Use when handling a database migration」。
- 反：「Trigger for A, B, C, D, E, and requests to …」，五组触发词等于没有触发条件。
- 反：description 里解释「需要 ReviewTable 确认」「分两阶段执行」，那是正文的事。
- 反：三个 skill 的 description 都覆盖「打开网页并交互」，模型只能靠猜。

**T8 Skill 正文看长短，长了才拆。** 短 skill 一页铺开就好，不必折腾成路由器；正文明显超过一两百行时，主干留在 SKILL.md，长细节和只在某条分支才用的内容进 `references/`，让模型知道去哪找而不必全读。
- 反：40 行的 skill 拆成 5 个 reference 文件。
- 反：400 行 SKILL.md 把所有分支的细节全铺开，每次加载都吃满。

**T9 工具描述：接口胜过教程。** 参数、枚举、schema 本身就是说明；description 只写 schema 表达不了的事。
- 反：description 里逐个复述 schema 已有的参数含义，再附三段示例调用。
- 反：description 里重复 CLAUDE.md 已写的项目规则。

**T10 判归属再落笔。** 先问：下一个 Agent 会因此做出不同决定吗？不会就不记。会，再选唯一主人：
- **不记**：已有可靠来源、已完工进度、一次性上下文、可直接推断的内容。
- **进 skill / 工具**：只在某个流程或工具里改变行为的知识；重写原有决策结构，不追加原始笔记。
- **进预置**：同时满足跨领域、改变决策、几乎每轮成立；门槛最高。
- **进外部**：偶尔需要但重新推导昂贵的参考知识；保持链接、新鲜度和唯一来源。

**T11 重构，不追加。** 吸收新知识时：一句话命名未来行为；找到放任旧错误发生的决策点（触发、路由、边界、反例或验证）；用最短表达重写该处；新知识能替代旧段落就删旧段落；最后检查断链、重复、私密信息、硬编码路径。
- 反：在 skill 末尾追加「注意：上次踩坑是……」的复盘段落；应收紧导致误判的那条路由条件。
- 反：把一篇长文的目录搬进 skill；应提炼成一条原则或少数锚定例。
- 反：公开 skill 里吸收个人路径、账号、客户或项目私有假设。

**T12 会过期的东西不留。** 判据：把日期抹掉，这条还成立吗？成立是教训，留；不成立是记录，删。
- 反：「已完成 PR #12，下一步做登录页」，git 历史已有。
- 反：「临时方案 / WIP / 待官方修复后移除」，对应的事早已 ship。
- 反：正文指引 Agent 去用的路径实测不存在（讲规则时举的示例路径不算）。

**T13 矛盾只认真冲突。** 同一场景、无作用域区分、给出相反指令才算；项目覆盖全局、显式例外、带条件的差异不算。规则自违反也算矛盾。
- 反：全局说文档前缀 `yyMMdd-`，项目 CLAUDE.md 说 `YYYYMMDD-`，且互不提及。
- 反：「不要硬编码用户名路径」的同一文件里出现 `/Users/xxx/`。
- 不算：「默认用 github，本项目走自建 host」，这是作用域覆盖。

**T14 auto-memory 中性。** 它是存储机制，不是好坏结论。偏好自动积累就查噪音、过期与容量；偏好人工整理就查维护成本与漏记。只评内容和行为，不因「自动」或「手动」本身扣分。

## 思想来源

- [Compound Engineering](https://github.com/EveryInc/compound-engineering-plugin/tree/main/skills/ce-compound)：把解决过的问题沉淀成可复用资产。
- [Matt Van Horn 的 push / pull memory 讨论](https://x.com/mvanhorn/status/2070966613994795489)：区分预置与按需记忆，强调人工整理与唯一归属。
- [Anthropic：The new rules of context engineering for Claude 5 generation models](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)：最小提示、模型判断、渐进披露、简洁工具描述与 auto-memory。
- [pvncher：Rethinking skills and prompts for GPT-6 Astra](https://x.com/pvncher/status/2095991462416490862)：description 越短越好、旧模型护栏是累赘、定义完成而不是要求停下审核。
