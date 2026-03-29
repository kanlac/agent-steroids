# Coding Agent 增强插件对比研究

> 对比 gstack、superpowers、oh-my-openagent 三个最知名的 Coding Agent 增强类项目

## 项目概览

| 维度 | superpowers | gstack | oh-my-openagent |
|------|-------------|--------|-----------------|
| **GitHub Stars** | 121,538 | 54,643 | 44,505 |
| **创建时间** | 2025-10 (最早) | 2026-03 (最晚) | 2025-12 |
| **语言** | Shell + Markdown | TypeScript | TypeScript |
| **License** | MIT | MIT | SUL-1.0 |
| **代码量** | 轻量 (Shell + Markdown) | 中等 (含编译二进制) | 200K+ 行 TypeScript |
| **核心定位** | 工程方法论框架 | 创业团队角色模拟 | 多模型编排引擎 |

## 创作者与项目气质

三个项目的方向差异，很大程度上来自创始人的职业背景。

### superpowers — Jesse Vincent (obra) → 工程纪律导向

开源界三十年老兵。创建了 Request Tracker（最广泛使用的开源工单系统）、Perl 6 项目经理、K-9 Mail 创始人（后被 Mozilla 收购为 Thunderbird for Android）、Keyboardio 机械键盘联合创始人。

**工程师出身，所以 superpowers 的核心是软件工程方法论**——TDD、根因分析、证据验证。它不关心你在做什么产品，只关心你怎么做工程。Simon Willison 称他为 "one of the most creative users of coding agents that I know"。121K stars，三者中最受欢迎。

### gstack — Garry Tan → 创业/产品导向

Y Combinator 现任 CEO。Stanford CS 毕业，Palantir 第 10 号员工，Posterous 联合创始人（被 Twitter 收购），Initialized Capital 创始人（种子投资了 Coinbase、Instacart、Flexport）。

**创业者和投资人出身，所以 gstack 的核心是从 idea 到上线的完整创业流程**——YC office hours 式产品构思、CEO/设计/工程三层审查、QA、部署、金丝雀监控。它模拟的不是一个工程团队，而是一个创业公司的完整班子。48 小时内突破 10K stars，TechCrunch 专文报道。

### oh-my-openagent — YeonGyu Kim (code-yeongyu) → 工具链/基础设施导向

韩国软件工程师，SW Maestro 毕业生（韩国科技部人才培养计划），先后在 StyleShare、Indent、Sionic AI 工作。个人投入约 $24,000 API token 研究最优多 agent 架构。

**基础设施工程师气质，所以 oh-my-openagent 的核心是重建 agent 运行时**——多模型路由、IDE 级工具链（LSP/AST-Grep）、48 个 lifecycle hooks。项目原名 oh-my-opencode，是 OpenCode（另一个团队的开源项目）的增强插件，后改名转向多平台多模型策略。2,555 个人 commits，开发强度惊人。

## 插件组件清单

### superpowers

14 个 skills + 3 个 commands + 1 个 agent，纯 Markdown + Shell，无编译产物。

**Skills (14)**

| Skill | 用途 |
|-------|------|
| using-superpowers | 入口 skill，建立技能发现和使用规范 |
| brainstorming | Socratic 式需求精炼，所有创造性工作前必须使用 |
| writing-plans | 将需求分解为 2-5 分钟的小任务，含完整代码示例和文件路径 |
| executing-plans | 按计划分批执行，设置人工检查点 |
| test-driven-development | RED-GREEN-REFACTOR 强制循环 |
| systematic-debugging | 4 阶段根因分析：调查→模式分析→假设→测试 |
| subagent-driven-development | 每个任务 spawn 独立子 agent，含双阶段审查（spec + quality） |
| dispatching-parallel-agents | 2+ 独立任务并行执行 |
| requesting-code-review | 派遣隔离上下文的代码审查子 agent |
| receiving-code-review | 处理审查反馈的规范流程 |
| using-git-worktrees | 创建隔离工作区，安全验证 |
| finishing-a-development-branch | 分支完成后的决策：merge / PR / keep / discard |
| verification-before-completion | 禁止未验证就声明完成 |
| writing-skills | 用 TDD 方法编写新 skill |

**Commands (3，已标记 deprecated，推荐直接用对应 skill)**

| Command | 对应 Skill |
|---------|-----------|
| /brainstorm | → brainstorming |
| /write-plan | → writing-plans |
| /execute-plan | → executing-plans |

**Agents (1)**

| Agent | 用途 |
|-------|------|
| code-reviewer | 高级代码审查员，评估架构、设计模式和代码质量 |

**Hooks**

- SessionStart hook：会话启动时注入 using-superpowers skill 内容
- 支持 Claude Code (`hooks.json`) 和 Cursor (`hooks-cursor.json`)

---

### gstack

29 个 skills + 1 个 agent，含编译二进制（持久化浏览器 daemon）。

**Skills (29)**

| 类别 | Skill | 用途 |
|------|-------|------|
| **规划** | office-hours | YC Office Hours 式产品构思，6 个 forcing questions |
| | plan-ceo-review | CEO/创始人视角审查计划，找到 10-star product |
| | plan-eng-review | 工程经理视角：锁定架构、数据流、边界情况、测试覆盖 |
| | plan-design-review | 设计师视角：每个维度 0-10 打分，说明满分长什么样 |
| | autoplan | 一键运行 CEO + 设计 + 工程三层审查 |
| **设计** | design-consultation | 从零构建设计系统，调研竞品并提出创意方案 |
| | design-review | 设计审计 + 自动修复循环，检测 AI slop |
| | design-shotgun | 生成多个设计变体，浏览器打开对比板 |
| **开发** | review | PR 审查：SQL 安全、LLM 信任边界、条件副作用 |
| | investigate | 系统化调试，4 阶段根因分析，3 次失败后停止 |
| | codex | 调用 OpenAI Codex 独立审查，跨模型二审 |
| **QA** | qa | 真实浏览器 QA：找 bug → 修复 → 生成回归测试 → 验证 |
| | qa-only | 仅报告，不修改代码 |
| **浏览器** | browse | 持久化 Chromium daemon，100-200ms 响应，cookie/session 持久 |
| | connect-chrome | 启动真实 Chrome + Side Panel 扩展，实时观察 agent 操作 |
| | setup-browser-cookies | 从 Chrome/Arc/Brave/Edge 导入 cookie 到 headless 会话 |
| **发布** | ship | 合并 base → 测试 → 审查 diff → 版本号 → CHANGELOG → PR |
| | land-and-deploy | 合并 PR → CI → 部署 → 验证生产健康 |
| | document-release | 自动更新所有项目文档匹配最新发布 |
| | setup-deploy | 一次性配置部署平台（Fly.io/Render/Vercel 等） |
| **监控** | canary | 部署后金丝雀监控：console 错误、性能回退、页面失败 |
| | benchmark | 性能基线：页面加载、Core Web Vitals、资源大小，PR 前后对比 |
| | retro | 周回顾：per-person 分析、shipping streaks、测试健康趋势 |
| **安全** | careful | 拦截 rm -rf、DROP TABLE、force-push 等危险命令 |
| | freeze | 锁定编辑范围到指定目录 |
| | guard | careful + freeze 组合 |
| | unfreeze | 解除 freeze 限制 |
| | cso | OWASP Top 10 + STRIDE 威胁建模，安全审计 |
| **维护** | gstack-upgrade | 自更新到最新版本 |

**Agents (1)**

| Agent | 用途 |
|-------|------|
| openai (Codex) | 通过 OpenAI Codex CLI 提供独立代码审查 |

---

### oh-my-openagent

7 个 skills + 8 个 commands + 11 个 agents + 26 个 tools + 48 个 hooks，200K+ 行 TypeScript。

**Agents (11)**

| Agent | 默认模型 | 用途 |
|-------|---------|------|
| Sisyphus | Claude Opus 4.6 / Kimi K2.5 | 主编排器，规划、委派、驱动任务完成 |
| Hephaestus | GPT-5.4 | 自主深度执行者，端到端完成目标 |
| Prometheus | Claude Opus 4.6 | 战略规划器，面试式提问，构建验证计划 |
| Oracle | GPT-5.4 | 架构决策、代码审查、调试（只读咨询） |
| Librarian | Minimax M2.7 | 多仓库分析、文档查找、OSS 实现示例 |
| Explore | Grok Code Fast 1 | 快速代码库探索和上下文搜索 |
| Multimodal-Looker | GPT-5.4 | 视觉内容分析：PDF、图片、图表 |
| Atlas | Claude Sonnet 4.6 | Todo-list 编排器，按计划系统执行任务 |
| Sisyphus-Junior | 按类别自动选模型 | 类别化子执行器 |
| Metis | Claude Opus 4.6 | 规划前补盲：发现隐藏意图、歧义、AI 失败点 |
| Momus | GPT-5.4 | 计划审查：验证清晰度、可验证性、完整性 |

**自动模型路由（Category 系统）**

| 类别 | 默认模型 | 场景 |
|------|---------|------|
| visual-engineering | Gemini 3.1 Pro | 前端、UI/UX |
| ultrabrain | GPT-5.4 xhigh | 深度逻辑推理 |
| deep | GPT-5.3 Codex | 目标驱动自主问题解决 |
| artistry | Gemini 3.1 Pro high | 高创意任务 |
| quick | GPT-5.4 Mini | 单文件小改动 |
| writing | Gemini 3 Flash | 文档、技术写作 |

**Skills (7)**

| Skill | 用途 |
|-------|------|
| git-master | Git 专家：commit 架构、rebase、history 考古 |
| frontend-ui-ux | 设计师转开发者视角，bold typography + 配色 |
| agent-browser | 浏览器自动化 via agent-browser CLI |
| dev-browser | 持久页面状态的浏览器脚本 |
| playwright | Playwright MCP 浏览器自动化 |
| github-triage | GitHub issue 分类 |
| pre-publish-review | 发布前审查 |

**Commands (8)**

| Command | 用途 |
|---------|------|
| /init-deep | 自动生成层级化 AGENTS.md 知识库 |
| /start-work | 从 Prometheus 计划开始执行，Atlas 编排 |
| /ralph-loop | 自循环直到任务 100% 完成 |
| /ulw-loop | ultrawork 模式循环 |
| /cancel-ralph | 取消 Ralph Loop |
| /stop-continuation | 停止所有循环机制 |
| /refactor | LSP + AST-Grep + 架构分析 + TDD 验证的智能重构 |
| /handoff | 创建上下文摘要用于下次会话继续 |

**Tools (26)**

| 类别 | Tools |
|------|-------|
| 代码编辑 | hashline-edit (哈希锚定行编辑), ast-grep (AST 感知重构) |
| 分析 | lsp (语言服务器: rename/goto/diagnostics), grep, glob |
| 执行 | interactive-bash, task (委派给 agent), background-task (并行) |
| 导航 | look-at (查看代码), session-manager (状态追踪) |
| 集成 | call-omo-agent, skill, skill-mcp, slashcommand, delegate-task |

**Hooks (48)**，覆盖 session 生命周期、tool guard、context transform、continuation 等层级，部分关键 hooks：

| Hook | 用途 |
|------|------|
| ralph-loop | 自循环管理 |
| atlas | Todo 编排与执行追踪 |
| comment-checker | 禁止 AI slop 注释 |
| compaction-context-injector | 压缩时自动注入 AGENTS.md 上下文 |
| hashline-edit-diff-enhancer | 增强 hashline 编辑的 diff 展示 |
| anthropic-context-window-limit-recovery | context window 超限恢复 |
| todo-continuation-enforcer | agent 空闲时自动拉回 |
| write-existing-file-guard | 写入已有文件的防护 |
| thinking-block-validator | thinking block 验证 |
| preemptive-compaction | 预防性上下文压缩 |

**内置 MCP (3)**

| MCP | 用途 |
|-----|------|
| Exa Web Search | 高质量网页搜索 |
| Context7 | 框架/库文档查询 |
| Grep.app | GitHub 跨仓库代码搜索 |

## 功能矩阵

| 能力 | superpowers | gstack | oh-my-openagent |
|------|:-----------:|:------:|:---------------:|
| **TDD 强制** | ★★★ | ☆ | ★ |
| **产品规划/审查** | ★★ | ★★★ | ★★ |
| **代码审查** | ★★ | ★★★ | ★★ |
| **浏览器自动化** | ☆ | ★★★ | ★★ |
| **安全防护** | ☆ | ★★★ | ★ |
| **多模型协作** | ☆ | ★ | ★★★ |
| **LSP/AST 工具** | ☆ | ☆ | ★★★ |
| **部署流水线** | ☆ | ★★★ | ☆ |
| **多平台支持** | ★★★ | ★ | ★★ |
| **自主循环执行** | ☆ | ☆ | ★★★ |

## 如何选择

### 选 superpowers：工程纪律优先

- 希望 AI 严格遵循 TDD、先调查再修复、先验证再声明完成
- 在多个 Coding Agent 平台间切换（Claude Code、Cursor、Codex、OpenCode、Gemini）
- 偏好渐进式采用，可以只用其中几个 skill

### 选 gstack：产品交付优先

- 需要从产品构思到生产部署的完整覆盖（创始人/技术负责人场景）
- 需要真实浏览器 QA（登录态、SPA）和安全审计
- 需要部署流水线：PR → 生产验证 → 金丝雀监控

### 选 oh-my-openagent：工具能力优先

- 拒绝单一模型锁定，想让任务自动路由到最合适的模型
- 需要 IDE 级别工具（LSP rename/goto/references、AST-Grep）
- 追求极致自主性，希望 agent 自主循环直到完成

### 组合使用

三者并非互斥。superpowers 的工程方法论 + gstack 的浏览器/部署能力互补性强，superpowers 适合作为基础层叠加其他工具。

## 总结

| | superpowers | gstack | oh-my-openagent |
|--|-------------|--------|-----------------|
| **本质** | 工程方法论 | 创业团队模拟 | 多模型编排引擎 |
| **类比** | 工程手册 | 创业公司编制表 | Agent 操作系统 |
| **创始人气质** | 开源工程师 | 创业者/投资人 | 基础设施工程师 |
| **优势** | 轻量、纪律性强、多平台 | 端到端产品交付、浏览器、安全 | 多模型、IDE 工具、自主性 |
| **劣势** | 无浏览器/部署能力 | 仅 Claude Code | 最重、复杂度高 |
