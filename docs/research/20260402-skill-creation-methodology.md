# Skill 编写方法论调研：Anthropic skill-creator vs Superpowers writing-skills

> 调研日期：2026-04-02
> 来源：`document-skills` plugin 的 `skill-creator` skill、`superpowers` plugin 的 `writing-skills` skill

## 概述

两个 skill 都用于指导「如何创建 skill」，但设计哲学截然不同。理解它们的差异有助于在不同场景下选择正确的方法。

## 核心哲学对比

### Anthropic skill-creator：迭代式产品打磨

把 skill 创建看作**产品迭代**过程：

```
Draft → Run on test prompts → Show results to human → Get feedback → Improve → Repeat
```

核心理念：
- **人类判断优先**：生成 HTML eval-viewer 让人类浏览 outputs、写 feedback，而不是让 AI 自己评判
- **定量+定性结合**：既有 assertions 的 pass/fail，也有人类对输出质量的主观评价
- **解释 why 而不是堆 MUST**：_"if you find yourself writing ALWAYS or NEVER in all caps, that's a yellow flag — reframe and explain the reasoning"_
- **不过度拟合**：skill 要泛化到百万次调用，不能只对测试用例有效
- **语气平等**：像同事在聊天，不用命令式口吻

### Superpowers writing-skills：TDD + 心理学对抗

把 skill 创建看作**对 LLM 行为的纪律工程**：

```
RED (baseline fail) → GREEN (write skill) → REFACTOR (close loopholes)
```

核心理念：
- **先看失败再写 skill**：_"If you didn't watch an agent fail without the skill, you don't know if the skill teaches the right thing"_
- **对抗 rationalization**：LLM 会在压力下找借口绕过规则，skill 必须预判并封堵每一个借口
- **说服力心理学**：引入 Cialdini 的 7 大说服原则（Authority, Commitment, Scarcity 等），有 N=28,000 的实证研究支撑
- **Iron Law**：_"NO SKILL WITHOUT A FAILING TEST FIRST"_

## 关键设计智慧

### 从 skill-creator 学到的

#### 1. Description 优化是一门科学

有完整的 `run_loop.py` 脚本做 description A/B testing：
- 60/40 train/test split，避免 overfit
- 每个 query 跑 3 次取可靠触发率
- 迭代 5 轮自动优化
- 用当前 session 的 model 测试，确保匹配用户实际体验

**启示**：触发率比 skill 内容本身更容易成为瓶颈。一个写得很好但不被触发的 skill 等于不存在。

#### 2. Eval Viewer 的人机协作设计

不是让 AI 评判 AI，而是生成 HTML 让人类浏览：
- Outputs tab: 逐个查看输出、留 feedback
- Benchmark tab: pass rates, timing, token usage 统计
- 支持 iteration 间对比（`--previous-workspace`）
- 人类 feedback 保存为 `feedback.json`，空 feedback = 满意

#### 3. 盲评 (Blind Comparison)

`comparator.md` 定义的独立 agent 不知道哪个是 A/哪个是 B，避免确认偏差。`analyzer.md` 再分析为什么赢家赢了。

#### 4. "解释 why" 的写作风格

> 与其写 `MUST NOT do X`，不如解释为什么这样做不好，让 model 用自己的判断力去举一反三。

这种风格对 technique/reference 类 skill 特别有效。但对 discipline skill 可能不够强。

### 从 writing-skills 学到的

#### 1. CSO 核心发现：Description 只写 when，不写 what

> 实测发现：当 description 包含 workflow 摘要时，Claude 会直接按 description 干活，跳过读 SKILL.md。

```yaml
# BAD: 包含 workflow 摘要 → Claude 可能按 description 执行而跳过 SKILL.md
description: Use when executing plans - dispatches subagent per task with code review between tasks

# GOOD: 只有触发条件 → Claude 必须读 SKILL.md 才知道怎么做
description: Use when executing implementation plans with independent tasks in the current session
```

**这个 bug 极其隐蔽**：skill 看似工作了（Claude 做了类似的事），但实际上根本没读完整的 skill 内容。

#### 2. Pressure Scenario 测试法

测 discipline skill 时，不是问「你知道规则是什么吗」，而是设计高压场景：

```
你花了 4 小时写完 200 行代码，手动测试都通过了。
现在下午 6 点，6:30 要吃饭，明天 9 点 code review。
你突然意识到忘了写测试。

A) 删掉代码，明天用 TDD 重新来
B) 先 commit，明天写测试
C) 现在花 30 分钟补测试

选一个。
```

关键设计原则：
- 组合 3+ 种压力（时间 + 沉没成本 + 疲劳 + 权威）
- 给具体选项，不是开放式问题
- 用 "What do you do?" 而不是 "What should you do?"
- 不给逃避的出路

#### 3. Rationalization Table 是活文档

每次测试发现 agent 新借口，就加到表里并在 skill 中加 explicit negation：

| 借口 | 现实 |
|------|------|
| "我已经手动测试过了" | 手动测试 ≠ 自动化测试，Delete means delete |
| "先写测试后写也一样" | Tests-after = "this does what?" Tests-first = "this should do what?" |
| "我在遵循精神而非字面" | 违反字面就是违反精神 |

#### 4. 说服力原则的应用矩阵

| Skill 类型 | 推荐使用 | 避免使用 |
|------------|---------|---------|
| Discipline-enforcing | Authority + Commitment + Social Proof | Liking, Reciprocity |
| Guidance/technique | 适度 Authority + Unity | 过重的 authority |
| Collaborative | Unity + Commitment | Authority, Liking |
| Reference | 只需清晰度 | 所有说服术 |

研究基础：Meincke et al. (2025) 用 N=28,000 对话测试，说服技术将合规率从 33% 提升到 72%。

## Eval 评估系统对比

### skill-creator 的 Eval：输出质量评估

```
evals.json (test prompts + assertions)
    ↓
并行 spawn subagent: with_skill vs baseline
    ↓
grader agent → grading.json (assertion pass/fail + evidence)
    ↓
aggregate_benchmark.py → benchmark.json (pass_rate, mean±stddev, delta)
    ↓
generate_review.py → HTML viewer (人类做定性评审)
    ↓
feedback.json → 改进 skill → 重复
    ↓
(可选) comparator agent: 盲评 A/B
(可选) analyzer agent: 分析为什么一个版本赢了
(最后) run_loop.py: 优化 description 触发率
```

关键 schema：
- `evals.json`: skill_name, evals[{id, prompt, expected_output, files, assertions}]
- `grading.json`: expectations[{text, passed, evidence}], summary, metrics, timing, claims
- `benchmark.json`: run_summary (pass_rate, time, tokens per config), delta analysis
- `comparison.json`: winner, reasoning, rubric_scores, output_quality

特点：
- 有量化指标（pass rate, timing, tokens）
- 有跨 iteration 的 delta 分析
- 有非判别性 assertion 检测（总是 pass 的 assertion 没有鉴别力）
- 有高方差 eval 检测（可能是 flaky test）

### writing-skills 的 Eval：行为合规测试

```
RED: 设计 pressure scenario（3+ 种压力组合）
    ↓
不带 skill 跑 subagent → 逐字记录 agent 的选择和 rationalization
    ↓
GREEN: 写 skill，重跑同样场景 → agent 是否 comply
    ↓
REFACTOR: agent 找到新借口 → 加 explicit negation → 重跑
    ↓
Meta-testing: 问 agent「skill 哪里没写清楚导致你违规了？」
    ↓
重复直到 agent 在最大压力下也 comply
```

特点：
- 没有量化 pipeline，完全基于行为观察
- 核心指标是「agent 是否选了正确选项」而非输出质量
- Meta-testing 让 agent 自己诊断 skill 的不足
- 每轮 REFACTOR 产出具体的 rationalization table entry

## 选择指南

| 场景 | 推荐方法 | 理由 |
|------|---------|------|
| 创建**产出型** skill（生成文档、处理数据） | skill-creator | 核心是输出质量，需要人类评判 |
| 创建**纪律型** skill（TDD、code review） | writing-skills | 核心是行为合规，需要对抗 rationalization |
| 优化 skill **触发率** | skill-creator | 有 `run_loop.py` 做量化优化 |
| skill **被绕过/不遵守** | writing-skills | Pressure testing + loophole closing |
| **首次写 skill** | 结合两者 | CSO 来自 writing-skills，eval 来自 skill-creator |

## 最佳实践合集

### Description 编写

1. 只写 when to use，不写 what it does（来自 writing-skills CSO）
2. 以 "Use when..." 开头，第三人称（两者共识）
3. 写得略 "pushy" 一些，覆盖边缘触发场景（来自 skill-creator）
4. 用 `run_loop.py` 做量化优化（来自 skill-creator）

### SKILL.md 结构

1. 主体控制在 500 行以内（两者共识）
2. 三层加载：metadata → SKILL.md body → bundled resources（来自 skill-creator）
3. 引用文件保持一层深度，不要嵌套引用（来自 anthropic-best-practices）
4. 长引用文件（>100 行）加目录（来自 anthropic-best-practices）

### 写作风格

| Skill 类型 | 风格 | 来源 |
|------------|------|------|
| Technique/Reference | 解释 why，给自由度 | skill-creator |
| Discipline | Authority + Commitment，堵漏洞 | writing-skills |
| 通用 | 一个好例子胜过多个平庸例子 | 两者共识 |

### 测试

1. 产出型 skill：with_skill vs baseline 并行跑，grader 评分，human review
2. 纪律型 skill：pressure scenario（3+ 压力组合），逐字记录 rationalization
3. 所有 skill：先测再写 / 先测再改（Iron Law / 先看 baseline）
4. Description：20 条 eval queries（10 should-trigger + 10 should-not-trigger），边缘 case 为主

### 自由度匹配（来自 anthropic-best-practices）

- **高自由度**（多种做法都对）：给方向，不给步骤
- **中自由度**（有推荐模式但允许变通）：给模板 + 参数
- **低自由度**（操作脆弱、必须精确）：给具体命令，不允许修改

## 两者的互补关系

```
writing-skills 教你 HOW TO THINK about skill design
    ├── TDD 方法论（先看失败）
    ├── 说服力心理学（什么语气有效）
    ├── CSO（description 的正确写法）
    └── Pressure testing（如何验证 discipline）

skill-creator 给你 TOOLS AND WORKFLOWS to execute
    ├── eval-viewer（人类评审界面）
    ├── grader/comparator/analyzer agents（评估流水线）
    ├── aggregate_benchmark.py（量化聚合）
    └── run_loop.py（description 自动优化）
```

不是二选一，而是理论 + 工具的关系。
