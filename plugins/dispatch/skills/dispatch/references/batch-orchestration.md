# 批次调度（Batch Orchestration）：模型、推理强度与编排表

模型和 effort 是两个独立旋钮：模型决定能力边界、专长与成本，effort 决定本次任务投入多少推理和自检。先匹配任务特长，再结合歧义、验错难度、失败代价和吞吐要求选择模型，最后选择 effort。

## 模型推荐表

这不是从上到下的等级或回退顺序。专项模型和高性价比模型可能比更强的通才更适合当前工作。

| 任务信号 | 推荐候选 | 选择理由 |
|---|---|---|
| 高歧义设计、复杂跨模块实现、长周期自治或高代价最终判断 | GPT-5.6 Sol、Opus | 面向复杂专业工作和长链路 Agent 任务，适合综合推理上限比专项优势更重要的场景 |
| 日常编码、代码库探索、资料分析和工具调用 | GPT-5.6 Terra、Sonnet | 能力、速度和成本较平衡，适合没有更强专项信号的常规专业工作 |
| 成本敏感，但仍需要较强编码和 Agent 执行能力 | DeepSeek V4 Pro | 调用成本明显低于多数高能力候选，同时针对生产环境中的 Agent 任务做了增强 |
| 授权范围内的代码安全审查、漏洞发现、攻击链或利用链分析 | GLM 5.3 | 官方评测显示其网络安全能力增长突出，尤其擅长漏洞发现和利用链后段；这类任务可优先于更强的通才 |
| 规则清楚、低风险、可验证、高吞吐的简单任务；尤其涉及图片、文档或界面反馈 | GLM 5.3 Flash | 当前 Flash 版本以较少计算提供较强的编码、工具使用、自动化和原生多模态能力，是“干活好且便宜”这一类 worker 的代表候选 |

输入很长、输出很多或文件数量大，不自动选择最强通才；规则清楚且验收可靠时，优先考虑高性价比模型。反过来，代码量很小但语义含糊、缺少可靠验错手段，也可能需要 Sol 或 Opus。

这些是起始候选，不是永久排名。模型版本、价格和工具适配会变化；派发前以当前 runtime 的可用列表为准。厂商评测只能说明值得优先试用，关键工作仍按真实任务的完成质量、重试和复核成本校准。安全审查尤其要用可复现输入或工具证据核验发现。

## 统一 effort 标尺

所有模型使用同一判断标准；runtime 不支持某个名称时，向下映射到最接近的可用档位。

| Effort | 什么时候用 |
|---|---|
| `low` | 单一路径、局部明确、错误易发现且可低成本重试；检索、分类、机械搬运 |
| `medium` | 有若干约束或工具步骤，但目标和验收清楚 |
| `high` | 存在方案歧义、跨模块因果或棘手边界，需要主动质疑假设，而外部验收可能漏错 |
| `xhigh` | 最难的长链路自治、开放式研究或高代价决策；需要广泛探索，且 `high` 已知不够 |

先修正互相冲突的任务说明、模糊的停止条件和无边界的工具范围，再提高 effort。高 effort 只是计算投入，不是质量保证。

有重复样本时，固定任务与验收后比较相邻档位。按完成一个合格任务的总成本衡量，计入失败调用、重试、返工和复核；重点看最难的一成任务，而不是每 token 单价。

## 编排表

派出 4 个及以上 agent 时，选好模型和 effort 后汇成一张表交给用户确认再开跑。一行一个任务：

| 阶段 | 任务 | 执行者（模型 / 强度 / 派发方式） | 评审链 | 状态 |
|---|---|---|---|---|

- **强度必须是运行时真正生效的值。** 设置位置因 runtime 而异（如 Claude Code 子代理的 effort 写在 agent 定义里，
  派发调用只能选模型；OpenCode 的 `--variant` 要用够难的题，对比不同档位下事件流 `tokens.reasoning` 是否随之变化，简单题噪声大不能作证）。验证不生效就标「未生效」。
- **实施与评审分列。** 评审链按先后列出每一级的模型 / 强度 / 方式，每级都要 PASS，标注轮次上限和
  「至少一个某模型循环至通过」这类硬要求。
- **状态**区分已定、待确认、试验。未经用户拍板的标「待确认」，不与已定项混排；首次使用的模型标「试验」，
  并写清质量不达标时的升级路径和报告义务。

## 依据

- [OpenAI：Codex subagents 的模型与 effort 选择](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [OpenAI：模型目录](https://developers.openai.com/api/docs/models)
- [Anthropic：Choosing the right model](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model)
- [Anthropic：Effort](https://platform.claude.com/docs/en/build-with-claude/effort)
- [Anthropic：Optimizing for cost and intelligence](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence)
- [DeepSeek：V4 Pro 正式版](https://api-docs.deepseek.com/news/news260813/)
- [DeepSeek：V4 模型与价格](https://api-docs.deepseek.com/quick_start/pricing)
- [Z.ai：GLM 5.3 官方仓库与模型说明](https://github.com/zai-org/GLM-5)
- [Z.ai：GLM 5.3 Flash](https://z.ai/blog/glm-5.3-flash)
