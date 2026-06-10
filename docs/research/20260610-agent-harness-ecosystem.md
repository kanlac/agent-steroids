# Agent 底座生态：Framework vs Harness vs 成品

> 调研日期：2026-06-10
> 主题：如果要自己搭一个 agent，该基于什么底座？厘清"编排框架 / harness / 成品"三层，以及 pi、OpenClaw、LangGraph 等的真实定位。
> 注：本文与同目录 `20260329-agent-plugins-comparison.md`（coding agent 的**增强插件层**：superpowers/gstack/oh-my-openagent）是不同层级，互为补充。

## TL;DR

- **2026 年的范式已从"用框架自己拼 loop"转向"harness engineering"**。中间层（工具、检索、loop）被吸进 SDK/harness，开发者剩下的工作是 system prompt + skills + policy。
- MBZUAI 2026-05 的研究：一个生产 agent **~98.4% 是 harness 基础设施**（权限、上下文管理、沙箱、工具路由、恢复），只有 **~1.6% 是 AI 决策逻辑**。业界共识：**"the harness matters more than the model"**。
- **分层要分清**：编排框架（LangGraph/Mastra/Pydantic AI）是"库"，harness（pi）是"可 fork 的 agent 本体"，成品（OpenClaw）是"在 harness 上打包好外围组件的开箱即用产品"。
- **关键事实**：**OpenClaw 是基于 pi 做的成品**（README 致谢 pi 作者 Mario Zechner / pi-mono）。pi 是更底层、自定义度更高的 harness；OpenClaw 绑死了自己的 Gateway + IM adapter，自定义度低。两者不是一个层级。
- **自建底座选型**：要最大自定义 / 完全拥有执行逻辑 → **pi**；要开箱即用的成品 → **OpenClaw**（但你就得接受它的 harness 和适配器）；要嵌进自己后端的编排逻辑 → LangGraph(Python)/Mastra(TS)，但注意这层正被降级为 harness 底下的 runtime。

## 一、范式转变：framework → harness

一年前搭 agent 的默认套路：选框架 → 定工具 → 接 RAG → 写一堆胶水代码。复盘下来，一半时间花在跟 agent 实际工作无关的基础设施上。

2026 年中间这层基本消失了：
- SDK 自带工具层；
- skills 系统取代了前置的工具注册表；
- 更长的上下文窗口把向量检索挤出了默认位置。

剩给团队的只有 **system prompt、skills、以及"agent 被允许做什么"的 policy**。这就是 "harness engineering"——你在做的是 harness 工程，而不是用别人的默认值。

**harness 的定义**：包在 LLM 外面、管理"除模型推理之外一切"的软件基础设施——它拥有 loop，决定某个 tool call 是否执行，强制预算，管理上下文，提供可观测性。
- framework = 给你积木，让你自己拼这个 loop（控制力高但要 debug 第三方深层栈）。
- SDK = 把你接到别人的 loop 上。
- harness = 拥有 loop 的运行时容器。

## 二、分层模型（避免选错层）

| 层 | 是什么 | 代表 | 你的工作量 |
|----|--------|------|-----------|
| **编排框架 / 库** | 给你 building blocks，自己拼 agent 逻辑塞进应用 | LangGraph(Python)、Mastra(TS)、Pydantic AI、CrewAI、Agno | 最大，自己拼 loop |
| **Harness** | 可 fork 的 agent 本体，自带 loop+工具+UI，行为靠 markdown/扩展定义 | **pi**、Claude Agent SDK、Goose、OpenCode | 中，焊你的工具/平台 |
| **成品** | 在 harness 上打包好 Gateway、IM adapter、app、语音、沙箱，开箱即用 | **OpenClaw**、**Hermes**、Claude Code | 最小，但自定义度最低 |

选错层的典型错误：想"fork 一个 agent 本体来改"，却被推荐了 LangGraph（那是库，要你自己拼）；或想要"轻量可完全掌控的底座"，却上了 OpenClaw（成品，绑死外围）。

## 三、Star 数实测（GitHub API，2026-06-10）

> 用 API 实拉，不取博客 SEO 摘要数字。

| 项目 | 层 | 语言 | Stars | 建仓 |
|------|----|------|------:|------|
| openclaw/openclaw | 成品 | - | 377,708 | 2025-11 |
| NousResearch/hermes-agent | 成品（自进化）| Python | 189,393 | 2025-07 |
| anthropics/claude-code | 成品 | - | 131,158 | 2025-02 |
| openai/codex | 成品/harness | - | 89,748 | 2025-04 |
| **earendil-works/pi** | **harness** | TS | **61,003** | 2025-08 |
| langchain-ai/langgraph | 编排框架 | Python | 34,222 | 2023-08 |
| mastra-ai/mastra | 编排框架 | TS | 24,891 | 2024-08 |
| langchain-ai/deepagents | harness（架在 LangGraph 上）| Python | 24,228 | 2025-07 |
| pydantic/pydantic-ai | 编排框架 | Python | 17,633 | 2024-06 |
| clacky-ai/openclacky | 成品/harness | Ruby | 945 | 2025-12 |

**读数**：harness/成品阵营（OpenClaw 37.8 万、Hermes 18.9 万、Claude Code 13.1 万、Codex 9 万、pi 6.1 万）整体碾压编排框架阵营（LangGraph 3.4 万、Mastra 2.5 万、Pydantic AI 1.8 万）。star 的引力已整体搬到 harness 这一侧。

## 四、关键认知修正：pi 与 OpenClaw 的关系

- **OpenClaw 基于 pi**。OpenClaw README 明确致谢："*Special thanks to Mario Zechner for his support and for pi-mono*"——Mario Zechner 即 pi（earendil-works/pi）作者。OpenClaw 的 agent 核心建立在 pi-mono 之上。
- **OpenClaw 在 pi 之上打包的外围**：local-first Gateway 控制面、20+ IM 渠道适配器（WhatsApp/Telegram/Slack/Discord…）、多平台 companion app（Win/macOS/iOS/Android）+ 语音唤醒 + Canvas、浏览器自动化/cron/skills registry、Docker/SSH/OpenShell 沙箱。
- **结论**：OpenClaw 是面向"个人单用户助手"的**成品**，开箱即用但自定义度低（你得用它的 harness 和它的 IM adapter）。pi 是更底层的 harness，自定义度高、完全可掌控——**两者不是一个级别的东西**。

> 衍生判断：如果你的目标是"深度自定义 / 完全拥有执行逻辑 / 自己接飞书等非主流 IM"，应基于 **pi**，而不是 fork OpenClaw 后跟它的成品结构较劲。

### 成品阵营里的另一条路线：Hermes（自进化）

- **NousResearch/hermes-agent**（Python, 18.9 万★, 2025-07），slogan "The agent that grows with you"，由 Nous Research 出品，**独立实现、不基于 pi**——与"基于 pi 的 OpenClaw"是成品层里两条不同的技术路线。
- **差异化在"闭环学习"**：唯一自带 learning loop 的 agent——从经验**自动创建并改进 skill**、维护持久记忆并定期"nudge"自己沉淀知识、可检索自己过往会话做跨会话召回。
- **开箱即用面**：多模态原生接入 CLI / Telegram / Discord / Slack / WhatsApp / Signal，经 OpenRouter 支持 200+ 模型，内置 cron 做自治任务，$5 VPS 到 serverless 都能跑。
- **与飞书相关**：原生 IM 列表里**同样没有飞书/Lark**，要接飞书仍需自己加适配器（和 pi/OpenClaw 一样）。
- **定位**：如果你要的是"会自我进化的个人助手成品 + 多 IM 开箱即用"，Hermes 是 OpenClaw 之外最值得评估的成品；但和所有成品一样，深度自定义不如基于 pi 自建。

## 五、连框架阵营自己都在转向 harness

LangChain 把重心从 LangChain 挪到 LangGraph（运行时）+ LangSmith（观测），并推出 **DeepAgents——一个架在 LangChain/LangGraph 之上的 harness**。即框架阵营的头部也在用脚投票，往 harness 叠。

所以 **LangGraph 不是"死了"，而是被降级为 harness 底下的 runtime/编排层**。在"纯框架、要最大灵活性和模型可移植性"这一格它仍是首选；但作为"要直接 build on 的 agent 本体"，2026 的答案是 harness，不是它。

## 六、自建底座选型建议

| 你的目标 | 推荐底座 | 理由 |
|----------|---------|------|
| 最大自定义 / 完全拥有 loop / 接非主流 IM（如飞书）| **pi**（TS, 6.1 万★）| 薄 harness（system prompt+工具 <1k token），行为靠 markdown+TS 扩展定义，自带 Discord/Telegram 桥接可照抄。OpenClaw 的底座本身。 |
| 要开箱即用的个人助手成品 | **OpenClaw**（37.8 万★, MIT）| 20+ IM adapter、Gateway、多端 app、语音、沙箱全打包。代价：自定义度低，绑死其结构。基于 pi。 |
| 要"会自我进化"的个人助手成品 + 多 IM 开箱 | **Hermes**（18.9 万★, Python）| 自带 learning loop（造 skill/持久记忆/跨会话召回）+ 原生多 IM + cron 自治。独立实现，不基于 pi。深度自定义仍不如基于 pi 自建。 |
| 要 Anthropic 官方 SDK 路线 | **Claude Agent SDK**（原 Claude Code SDK）+ Managed Agents | 官方背书、生态成熟。 |
| 要嵌进自己后端的编排逻辑 / 最厚生产背书 | **LangGraph**(Python) / **Mastra**(TS) | 企业部署名单最长（Klarna/Uber/JPMorgan…）。但属"库"层，且正被 harness 叠在上面。 |

### 接飞书（Feishu/Lark）补充
pi **不原生支持飞书**；其聊天桥接在独立仓库 `earendil-works/pi-chat`，目前只有 Discord + Telegram。但 pi 把"agent 运行时（pi-agent-core）"与"聊天平台"解耦，接飞书=照现有适配器写一个飞书 adapter（飞书事件订阅 → 映射成 AgentMessage → 经飞书 OpenAPI 回包），工作量中等、自包含，不动核心。难点在飞书自身那套（验签、tenant_access_token 刷新、卡片消息），与 pi 无关。

## 信息源

- earendil-works/pi — https://github.com/earendil-works/pi ；聊天桥接 earendil-works/pi-chat（仅 Discord+Telegram）
- openclaw/openclaw — https://github.com/openclaw/openclaw （README 致谢 pi-mono / Mario Zechner）
- NousResearch/hermes-agent — https://github.com/NousResearch/hermes-agent （"The agent that grows with you"，自进化闭环；本地 `~/.hermes`）
- langchain-ai/deepagents — https://github.com/langchain-ai/deepagents
- "How Building AI Agents Has Changed in 2026"（Pulumi）— https://www.pulumi.com/blog/how-building-ai-agents-has-changed/
- "All Agent Harnesses: The Live Comparison"（htek.dev）— https://htek.dev/articles/all-agent-harnesses-live-comparison
- "Deep Agents: The Harness Behind Claude Code, Codex, Manus, and OpenClaw"（Medium / Agent Native）
- MBZUAI 2026-05 研究（生产 agent ~98.4% harness / ~1.6% AI 逻辑，经多篇 harness 对比文转述）
- Star 数：GitHub REST API `/repos/{owner}/{repo}`，2026-06-10 实拉
