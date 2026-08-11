---
name: hippocampus
description: |
  Manage an agent's context and memory across always-loaded instructions, auto-memory, tool definitions, skills, and references. Use for two distinct jobs: (1) diagnose and treat — audit, score, and declutter the current context environment, then require a ReviewTable confirmation before bulk changes; (2) absorb knowledge — route a correction, lesson, or “remember this” request to its proper owner and refactor it in place, without a report or confirmation table. Trigger for memory health checks, CLAUDE.md/AGENTS.md or skill cleanup, verbose tool descriptions, context engineering audits, and requests to record reusable lessons.
---

# Hippocampus

管理 Agent 记忆与上下文的海马体。它做两件事，授权不要混：

- **诊断与治疗**：批量体检，先出报告和治疗确认书，用户确认后才改。
- **吸收新知识**：用户的请求本身就是授权；判归属、重构落地、汇报结果，不生成报告或确认书。

## 黄金法则

1. **最短充分表达**：一行足够，就不写一段；一段足够，就不建一篇。每多一句都必须改变 Agent 的判断或行动。
2. **只教模型不知道的**：能从代码、目录、schema 或上下文推断出的内容不写；通用建议不写。
3. **把判断还给模型**：除高风险红线、非显然约束和脆弱流程外，写意图与边界，不堆规则、步骤和例子。
4. **一个事实一个主人**：工具规则住工具描述或对应 skill，项目规则住项目记忆；不在多处重复。
5. **按需披露**：常驻层只留路由和硬约束；skill 留主干；长细节放 reference；罕用工具能延迟加载就不常驻。
6. **接口胜过教程**：优先用清晰的参数、枚举、schema 和文件结构表达能力；例子只用于消除真实歧义。

## 两类上下文

- **预置记忆**：每轮进入上下文的全局/项目指令、auto-memory，以及当前会话中提前加载的工具描述与 schema。这里每个 token 都反复交税，必须稀缺。
- **外部记忆**：按需加载的 skill、reference、文档、可查询存储和延迟加载工具。它可以更丰富，但必须可检索、不过时、不冲突。

Auto-memory 是存储机制，不是好坏结论。偏好自动积累，就检查噪音、过期与容量；偏好人工整理，就检查维护成本与漏记。**只评内容和行为，不因“自动”或“手动”本身扣分。**

## 路由：这条知识该住哪

- **不记**：已有可靠来源、已完工进度、一次性上下文、模型可直接推断的内容。
- **进对应 skill / 工具**：只在某个流程或工具里改变行为的知识；重写原有决策结构，不追加原始笔记。
- **进预置**：同时满足跨领域、改变决策、几乎每轮成立；门槛最高。
- **进外部**：偶尔需要、重新推导昂贵的参考知识；保持链接、新鲜度和唯一来源。

## ① 诊断与治疗

1. **诊断**：只扫当前运行环境实际可达的上下文。用 `scripts/score-mechanical.py` 固定文件范围和机械候选，再按 `references/scoring-rubric.md` 裁决、记 findings 账本、生成报告。每个扣分都挂完整 `路径:行号` 与原文。
2. **确认**：按 `references/review-table.md` 生成 ReviewTable。方案无歧义的默认勾选；涉及偏好或目标的给明确选项，等待用户决定。
3. **治疗**：校验确认 JSON，只执行获批方案；旧报告保持定格。

扫描包括：当前目录会加载的 `CLAUDE.md` / `AGENTS.md` / auto-memory、可触达 skills 与文档，以及**当前会话实际可见的工具描述和输入 schema**。工具若延迟加载，归外部；若运行时不提供清单，就记 N/A，不猜、不因不可见扣分。环境很大时可按表面并行取证，最后统一做跨表面冲突裁决。

报告结构、渲染、范围与隐私 → `references/diagnosis-report.md`；确认书与治疗契约 → `references/review-table.md`。

## ② 吸收新知识

先跑上面的路由，再把知识重构进唯一主人。目标是让下次行为更准且上下文不增肥；若新知识能替代旧段落，就同时删旧段落。详细判断 → `references/absorb-knowledge.md`。

## 边界

- 分数是方向性参考；处方与证据比数字重要。
- 只管理上下文的归属、质量与加载方式，不规定项目的 wiki 结构。
- 默认全程本地；完整报告含原文，只用脱敏分享卡对外。

## 思想来源

- [Compound Engineering](https://github.com/EveryInc/compound-engineering-plugin/tree/main/skills/ce-compound)：把解决过的问题沉淀成可复用资产。
- [Matt Van Horn 的 push / pull memory 讨论](https://x.com/mvanhorn/status/2070966613994795489)：区分预置与按需记忆，强调人工整理与唯一归属。
- [Anthropic：The new rules of context engineering for Claude 5 generation models](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)：最小提示、模型判断、渐进披露、简洁工具描述与 auto-memory。
