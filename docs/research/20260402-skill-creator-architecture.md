# Skill Creator 架构与流程图

> 调研日期：2026-04-02
> 配套文档：[skill-creation-methodology.md](./20260402-skill-creation-methodology.md)

## 1. 主流程总览

```
Phase 0: Capture Intent & Interview
  [Human + Agent]
  │
  │  1. User describes the skill
  │  2. Agent writes SKILL.md draft
  │  3. Agent drafts 2-3 test prompts → evals/evals.json (主列表, prompts only)
  │
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    ITERATION LOOP                                   │
│                    (repeat until user is happy)                      │
│                                                                     │
│  Step 1: SPAWN RUNS ──────────────────────────────── [Subagents]    │
│  │                                                                  │
│  │  Per test case, spawn TWO subagents IN PARALLEL:                 │
│  │                                                                  │
│  │  ┌─────────────────────┐  ┌──────────────────────────┐           │
│  │  │  with_skill agent   │  │  baseline agent           │          │
│  │  │                     │  │                            │          │
│  │  │  • Reads SKILL.md   │  │  • No skill (new skill)   │          │
│  │  │  • Executes prompt   │  │    or old skill snapshot  │          │
│  │  │  • → with_skill/    │  │  • Same prompt             │          │
│  │  │    outputs/          │  │  • → without_skill/        │          │
│  │  └─────────────────────┘  │    outputs/                │          │
│  │                           └──────────────────────────┘           │
│  │                                                                  │
│  │  Creates: eval_metadata.json per eval dir (从 evals.json 同步)   │
│  │  每个 iteration 必须重建，不从上一轮继承!                         │
│  │  即使 prompt 没变，也要重建（因为 iteration 目录自包含）          │
│  │                                                                  │
│  ▼                                                                  │
│  Step 2: DRAFT ASSERTIONS ────────────────── [Agent, while waiting] │
│  │                                                                  │
│  │  • Don't just wait for runs — draft assertions now               │
│  │  • Objectively verifiable checks                                 │
│  │  • Update eval_metadata.json + evals/evals.json                  │
│  │                                                                  │
│  ▼                                                                  │
│  Step 3: CAPTURE TIMING ──────────────────── [Agent, as runs end]   │
│  │                                                                  │
│  │  • Each subagent notification has total_tokens + duration_ms     │
│  │  • Save to timing.json immediately (only chance!)                │
│  │                                                                  │
│  ▼                                                                  │
│  Step 4: EVALUATION PIPELINE ─────────────── [Agents + Scripts]     │
│  │                                                                  │
│  │  4a. Grade ─── grader subagent (agents/grader.md)                │
│  │  │             reads outputs + assertions                        │
│  │  │             → grading.json per run                            │
│  │  │                                                               │
│  │  4b. Aggregate ─── scripts.aggregate_benchmark                   │
│  │  │                 reads all grading.json + timing.json           │
│  │  │                 → benchmark.json + benchmark.md                │
│  │  │                                                               │
│  │  4c. Analyze ─── analyzer subagent (agents/analyzer.md)          │
│  │  │               surfaces hidden patterns:                       │
│  │  │               non-discriminating assertions, flaky evals      │
│  │  │                                                               │
│  │  4d. Launch Viewer ─── eval-viewer/generate_review.py            │
│  │                        → HTML in browser (Outputs + Benchmark)   │
│  │                        iteration 2+: --previous-workspace        │
│  │                        headless: --static output.html            │
│  │                                                                  │
│  ▼                                                                  │
│  Step 5: HUMAN REVIEW ──────────────────────────────── [Human]      │
│  │                                                                  │
│  │  ┌─ Outputs Tab ──────────┐  ┌─ Benchmark Tab ────────┐         │
│  │  │ • Per test case view   │  │ • Pass rates per config │         │
│  │  │ • Prompt + output      │  │ • Timing & token usage  │         │
│  │  │ • Previous output      │  │ • Per-eval breakdowns   │         │
│  │  │ • Formal grades        │  │ • Analyst observations  │         │
│  │  │ • Feedback textbox     │  │                         │         │
│  │  └────────────────────────┘  └─────────────────────────┘         │
│  │                                                                  │
│  │  "Submit All Reviews" → feedback.json                            │
│  │  (empty feedback = satisfied)                                    │
│  │                                                                  │
│  ▼                                                                  │
│  Step 6: IMPROVE SKILL ─────────────────────────────── [Agent]      │
│  │                                                                  │
│  │  a. Read feedback.json                                           │
│  │  b. Generalize (don't overfit to test cases)                     │
│  │  c. Read transcripts (bundle repeated helper scripts)            │
│  │  d. Revise SKILL.md (may also update eval prompts)               │
│  │                                                                  │
│  │  Exit if: user happy / all feedback empty / no progress          │
│  │  Otherwise → back to Step 1 with iteration-N+1/                  │
│  │                                                                  │
└──┼──────────────────────────────────────────────────────────────────┘
   │
   ▼
Optional: BLIND COMPARISON ────────────────────────── [Subagents]
  │
  │  comparator subagent (agents/comparator.md)
  │  • Sees two outputs without knowing A/B → comparison.json
  │
  │  analyzer subagent (agents/analyzer.md)
  │  • Explains why the winner won → analysis.json
  │
  ▼
Final: DESCRIPTION OPTIMIZATION ───────────────────── [Script]
  │
  │  1. Generate 20 trigger eval queries (10 should / 10 shouldn't)
  │  2. User reviews in HTML (assets/eval_review.html template)
  │     → exports eval_set.json
  │  3. Run: scripts.run_loop --eval-set ... --max-iterations 5
  │     • 60/40 train/test split
  │     • 3 runs per query for reliability
  │     • Auto-proposes description improvements
  │  4. Apply best_description (selected by test score, not train)
  │
  ▼
Final: PACKAGE ────────────────────────────────────── [Script]
  │
  │  scripts.package_skill → .skill file
  │
  ▼
  Done!
```

## 2. 目录结构

### skill-creator/ (工具本身)

```
skill-creator/
├── SKILL.md                       # 主指令文档
├── agents/
│   ├── grader.md                  # Step 4a: assertion 评判指令
│   ├── comparator.md              # Optional: 盲评 A/B 指令
│   └── analyzer.md                # Step 4c + 盲评后: 模式分析指令
├── scripts/
│   ├── aggregate_benchmark.py     # Step 4b: 聚合 grading → benchmark
│   ├── run_loop.py                # Final: description 自动优化
│   ├── package_skill.py           # Final: 打包 .skill 文件
│   └── utils.py                   # 内部工具: parse_skill_md()
├── eval-viewer/
│   └── generate_review.py         # Step 4d: 生成 HTML 评审界面
├── assets/
│   └── eval_review.html           # Final: description eval 模板
└── references/
    └── schemas.md                 # JSON schema 定义 (evals, grading, benchmark...)
```

### my-skill-workspace/ (每个 skill 一个，与 skill 目录平级)

```
my-skill/                                # skill 目录
├── SKILL.md
└── evals/
    └── evals.json                       # 主列表：所有 test case 定义（跨 iteration 维护）

my-skill-workspace/                      # workspace 目录（与 skill 目录平级）
├── iteration-1/
│   ├── descriptive-name-0/              # eval 目录（名字描述测试内容）
│   │   ├── eval_metadata.json           # 该 eval 的 prompt + assertions（从 evals.json 同步）
│   │   ├── with_skill/
│   │   │   ├── outputs/                 # skill 版本的输出
│   │   │   ├── grading.json             # assertion 评判结果
│   │   │   └── timing.json              # tokens + duration
│   │   └── without_skill/
│   │       ├── outputs/                 # baseline 输出
│   │       ├── grading.json
│   │       └── timing.json
│   ├── descriptive-name-1/
│   │   └── ...
│   ├── benchmark.json                   # 聚合统计
│   ├── benchmark.md                     # 人类可读统计
│   └── feedback.json                    # 人类评审结果
├── iteration-2/
│   ├── ...                              # 每个 eval 需要新建 eval_metadata.json!
│   └── feedback.json
└── skill-snapshot/                      # 旧 skill 备份（改进模式下）
```

**测试用例的两层存储：**

- `evals/evals.json` — **主列表**，在 skill 目录下，跨 iteration 持久维护。增删改 eval 都改这里。
- `eval_metadata.json` — **副本**，在每个 iteration 的每个 eval 目录下。使每个 iteration 目录自包含，viewer/grader 不需要回溯读 evals.json。

两者同步更新（Step 2）。改了 evals.json 中的 prompt 或 assertions 后，新 iteration 中对应的 eval_metadata.json 也要重建。

**Workspace 的本质：**

Workspace 不是"可精确复现的测试结果"，而是**一次评审过程的记录**。这跟代码的 CI 不同——CI 的测试是确定性的（pass/fail），而 skill eval 是概率性的（LLM 输出 + 人类判断）。凭 `evals.json` 可以重跑测试，但 outputs 不会完全一致（LLM 随机性），人类的 feedback 也不可复现。因此 workspace 通常不需要加入版本管理。需要持久保留的只有 skill 本身（`SKILL.md`）和测试定义（`evals/evals.json`）。

## 3. Scripts & Agents 速查表

| Name | Type | Used In | Input → Output |
|------|------|---------|----------------|
| `agents/grader.md` | Subagent 指令 | Step 4a: 评判 | eval_metadata.json + outputs/ → **grading.json** |
| `agents/comparator.md` | Subagent 指令 | Optional: 盲评 | 两组匿名 outputs → **comparison.json** |
| `agents/analyzer.md` | Subagent 指令 | Step 4c + 盲评后 | benchmark.json 或 comparison.json → **analysis.json** |
| `scripts.aggregate_benchmark` | Python | Step 4b: 聚合 | iteration-N/ (grading + timing) → **benchmark.json** + **benchmark.md** |
| `eval-viewer/generate_review.py` | Python | Step 4d: 展示 | iteration-N/ + benchmark.json → **HTML 评审页面** → feedback.json |
| `scripts.run_loop` | Python | Final: 优化触发 | eval_set.json + SKILL.md → **best_description** (JSON + HTML) |
| `scripts.package_skill` | Python | Final: 打包 | skill directory → **.skill 文件** |
| `scripts/utils.py` | Python | 内部工具 | SKILL.md → parsed name, description, content |

## 4. Eval Prompt 跨 Iteration 演进示例

```
Iteration 1 (初始)          Iteration 2 (修正)           Iteration 3 (扩展)
─────────────────           ─────────────────           ─────────────────
eval-0: 生成销售报告        eval-0: 不变                eval-0: 不变
eval-1: 做个趋势图          eval-1: 做个分区域堆叠      eval-1: 不变
  └─ 问题: 太模糊              柱状图,含坐标轴和图例
     输出不可比                 └─ 修正: 更具体
eval-2: 总结关键指标        eval-2: 删除                eval-3: 不变
  └─ 问题: baseline           └─ 原因: 无鉴别力
     也能做对                eval-3: 处理损坏的 xlsx     eval-4: 处理 50MB 大文件
                                └─ 新增: 来自 user          └─ 新增: 性能边界
                                   feedback              eval-5: 中文 locale 报告
                                                            └─ 新增: i18n 覆盖
```

**关键规则**：每个 iteration 目录下的 `eval_metadata.json` 必须重新创建。即使 prompt 没变，文件也不会从上一轮"继承"——每个 iteration 是自包含的。

## 5. 关键 JSON Schema 概览

### evals/evals.json (主列表，skill 级别)

```json
{
  "skill_name": "my-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "User's task prompt",
      "expected_output": "Description of expected result",
      "files": [],
      "assertions": [...]
    }
  ]
}
```

> 这是所有 test case 的 source of truth，跨 iteration 维护。增删改 eval 都改这里。

### eval_metadata.json (副本，iteration/eval 级别)

```json
{
  "eval_id": 0,
  "eval_name": "descriptive-name-here",
  "prompt": "The user's task prompt",
  "assertions": [...]
}
```

> 每个 iteration 的每个 eval 目录下一份。内容从 evals.json 同步而来，使 iteration 目录自包含。

### grading.json (单次 run 的评判结果)

```json
{
  "expectations": [
    { "text": "Output contains revenue chart", "passed": true, "evidence": "Found chart in output.docx page 2" },
    { "text": "Axis labels present", "passed": false, "evidence": "Y-axis has no label" }
  ],
  "summary": "1/2 assertions passed",
  "metrics": { ... },
  "timing": { ... },
  "claims": [ ... ],
  "notes": "...",
  "eval_feedback": "..."
}
```

> **注意**: expectations 数组必须用 `text`, `passed`, `evidence` 字段，viewer 依赖这些 field name。

### benchmark.json (聚合统计)

```json
{
  "run_summary": {
    "with_skill": { "pass_rate": 0.83, "mean_time": 45.2, "stddev_time": 8.1, "mean_tokens": 52000 },
    "without_skill": { "pass_rate": 0.42, "mean_time": 38.7, "stddev_time": 12.3, "mean_tokens": 41000 }
  },
  "delta": { "pass_rate": "+0.41", "time": "+6.5s", "tokens": "+11000" },
  "per_eval": [ ... ]
}
```

### timing.json (单次 run 的计时)

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3
}
```
