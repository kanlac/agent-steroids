# Pi Agent 框架调研(earendil-works/pi)

> 调研日期 2026-07-06,基于源码通读(`main` 分支,v0.80.x)。用于评估"自建 agent 底层 vs 套壳现成 CLM/CLI"的决策。相关生态对比见 `20260610-agent-harness-ecosystem.md`。

## 一句话定位

Pi 是一个 **TypeScript agent 框架**,可跑在 Node/Bun/浏览器/Worker。它不只是"agent loop 积木"——`coding-agent` 包已是一个**接近 Claude Code 的完整 harness**,自建 agent 时能省掉大量基础设施。

## 包结构(`packages/`)

| 包 | 作用 | 关键源码 |
|---|---|---|
| `ai` | 多 provider 统一 LLM API(Anthropic/OpenAI/Google/Bedrock/Groq/DeepSeek/Kimi… 数十家),含流式、reasoning、prompt cache、OAuth | `src/api/*`、`src/providers/*` |
| `agent` | agent 引擎 + harness:agent-loop、上下文压缩、会话持久化、skills、hooks、observability | `src/agent-loop.ts`、`src/harness/*` |
| `coding-agent` | 成品编码 agent:基础工具集 + 扩展系统 + 交互/无头模式 | `src/core/tools/*`、`examples/extensions/*` |
| `orchestrator` | 编排(多 agent) | — |
| `tui` | 终端 UI 库(差分渲染) | `src/components/*` |

## 开箱即用的能力(源码确认)

自建 agent 时**这些不用自己写**:

- **上下文压缩**:`agent/src/harness/compaction/`(branch-summarization 等)
- **会话持久化/续接**:`agent/src/harness/session/`(jsonl / memory 两种 repo)
- **planning / todo / plan-mode**:`coding-agent/examples/extensions/todo.ts`、`plan-mode/`
- **基础工具集**:bash / edit / read / write / grep / find / ls(`coding-agent/src/core/tools/`)
- **skills、hooks、observability**:`agent/src/harness/skills.ts`、`docs/hooks.md`、`docs/observability.md`(runtime-agnostic 的 span/trace,不绑 OTel/Sentry)
- **人在环 & 交互示例**:`question.ts`、`questionnaire.ts`、`permission-gate.ts`、`confirm-destructive.ts`、`timed-confirm.ts`
- **多 agent 编排示例**:`examples/extensions/subagent/`

**明确不含**:权限/沙箱系统(限制文件/进程/网络/凭证)。自建时须自己加固。

## 核心:给自定义前端(如 web)的事件流

自建 web/自定义 UI 时,通过 `Agent.subscribe()` 订阅 `AgentEvent`(源码 `agent/src/types.ts`):

```ts
type AgentEvent =
  | { type: "agent_start" }
  | { type: "agent_end"; messages }
  | { type: "turn_start" }
  | { type: "turn_end"; message; toolResults }
  | { type: "message_start"; message }
  | { type: "message_update"; message; assistantMessageEvent }  // 流式文本 + reasoning delta
  | { type: "message_end"; message }
  | { type: "tool_execution_start"; toolCallId; toolName; args }
  | { type: "tool_execution_update"; toolCallId; ...; partialResult }
  | { type: "tool_execution_end"; toolCallId; ...; result; isError };
```

reasoning/thinking 是一等公民,由 `ThinkingLevel: "off"|"minimal"|"low"|"medium"|"high"|"xhigh"` 控制。

## 两个高频产品需求的实现方式

### 1) 思考过程展示

- **数据全在事件流里**:`message_update`(思考/正文流式)、`tool_execution_*`(正在执行什么)、todo 扩展(计划清单)。
- **要自己做的只有渲染**:订阅事件→WebSocket/SSE→前端把事件映射成"思考区 / 进度条 / 正在执行 X"。任何方案都逃不掉这层,它就是产品 UI 本身。

### 2) 交互式提问清单(单选/多选,类似 Claude 官网)

Pi 把它实现为一个**注册工具**,现成示例 `questionnaire.ts` 的 schema 几乎等同 Claude 的 AskUserQuestion:

```ts
Question = { id, label /*tab标签*/, prompt, options:[{value,label,description}], allowOther }
questionnaire = { questions: Question[] }   // 多问题 = tab 切换
```

**关键机制(免费)**:工具的 `execute()` 返回 Promise;agent loop 天然在工具调用处**暂停**,直到工具 resolve 才继续。这正是"反问→等选择→再推进"的原理——一个"执行=问人"的工具。schema、暂停/恢复、模型主动发问的 prompt 引导全现成。

**关键限制**:现成示例是 **TUI 渲染**(源码里 `if (ctx.mode !== "tui") return "UI not available"`,走 `ctx.ui.custom` + pi-tui)。**web 端要自己重写 `execute()`**:不调终端渲染,而是 emit "待回答"事件到前端 → `await` 一个 Promise → 浏览器 POST 回答案时 resolve → 作为工具结果 return。诀窍一句话:**让 `execute()` 的 Promise 在 web 回调时 resolve,而非终端按键时**。

同一模式复用于人在环审批(permission-gate / confirm)。

## 自建时真正的剩余工作量(收敛为三块)

1. **Web 传输 + 渲染层**:事件流→SSE/WebSocket→前端;交互工具的 web 往返。
2. **领域工具**:业务特定的工具(如桌面自动化 Word/Chrome、内部系统集成),建议做成可移植模块。
3. **沙箱加固**:Pi 不含,须自建。

上下文管理、会话、planning、基础工具、provider 接线等此前常被高估的部分,Pi 白送。

## 选型建议(通用)

| 需求 | 推荐 |
|---|---|
| 一次性验证 / demo | 套壳现成 CLI(`claude -p --json` / `codex exec --json`),最快 |
| 做产品、要合规计费、要类型化事件、但接受"引擎是别人的" | 官方 SDK(如 Claude Agent SDK)+ API key |
| 要自主技术底层(融资叙事)、深度自定义 loop、掌控成本/模型路由、多 agent 编排 | Pi 自建 |

## Sources

- 仓库:https://github.com/earendil-works/pi
- 源码路径见上文(`packages/agent/src/types.ts`、`packages/coding-agent/examples/extensions/questionnaire.ts` 等,`main` 分支)
