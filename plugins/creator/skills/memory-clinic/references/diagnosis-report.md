# Diagnosis Report — scoring and rendering

How to turn a scan into the "记忆精神科确诊书" (the diagnosis report). The visual template is `assets/diagnosis-template.html`; this doc is the rubric and the fill guidance behind it.

## Principle: no evidence, no points

Every score is a claim, and every claim needs a receipt. Before deducting on any dimension, capture the concrete `file:line` and the quoted text that justifies it. The report shows those quotes inline under each dimension — that is what proves the diagnosis was computed from the user's real memory rather than pasted from a template. A dimension score with no cited lines is a bug.

Signals come in two kinds; keep them honest about which is which:

- **🔧 Mechanical (reproducible)** — line counts, file sizes, the 200-line rule, per-session token estimates, broken references, `@AGENTS.md`-import checks. Anyone re-running gets the same answer.
- **🧠 Semantic (judgment)** — "this line changes no decision", "this note is stale", "these two rules contradict". This is where the agent's taste shows. Label it as judgment, don't dress it up as measurement.

## The four dimensions

Each answers one distinct question — keep them non-overlapping (太大 / 没用说不清 / 过时 / 打架).

- **① 体量 Bloat** — size only. Per-file line count vs the ~200-line rule, total bytes, estimated tokens loaded per session, and the red line: is push so large the harness truncates it (so part never loads)? Mostly mechanical. Applies to any single file, push or pull.
- **② 可用性 Usability** — of the content that exists, how much changes a decision. Flag generic filler, anything inferrable from the repo, and instructions too vague to act on. Mostly semantic, with mechanical help (duplicate detection, boilerplate patterns).
- **③ 新鲜度 Freshness** — is it still true. Dead paths / renamed files (mechanical), finished-work records and expired "temporary/WIP/currently-using-X" claims (semantic).
- **④ 矛盾 Contradiction** — does anything contradict anything else, *including across push and pull*. Surface conflicts as **pairs**, each side quoted with its `file:line`. This is the highest-signal, most convincing finding — the "oh, I did write both" moment — so give it its own prominent section, laid out like a side-by-side diff (two columns, line numbers shown; for a demo, invented line numbers are fine).

## Rollup

```
per-dimension evidence
   → surface scores: 全局记忆 / 项目记忆 / 技能 / 文档   (each 0–100, shown directly)
   → push score (global+project)  and  pull score (skills+docs)
   → total = push : pull = 5:5     (0–100) + grade band
```

Weight 5:5 by default — do not presume which layer matters more for a given user. Name the surfaces in human terms (全局记忆 = the global CLAUDE.md), never "上半区/push" in the visible report.

Grade bands (psychiatric-diagnosis framing, tune copy to taste, keep it playful not mean):

| 分数 | 病情分级 |
|---|---|
| 90–100 | 脑回清奇（保持） |
| 75–89 | 轻度记忆囤积 |
| 60–74 | 记忆虚胖症 |
| 40–59 | 数字仓鼠症 |
| <40 | smooth brain 晚期 · 脑子进水 |

Always print a small disclaimer: the score is a **directional reference, not a precise measure** — mechanical items reproduce, semantic items depend on this run's judgment; the real value is the prescription, not the number.

## The report's sections (what the template fills)

The template is a psychiatric case-report ("确诊书"). Fill every section from real scan data — no placeholders left in a produced report:

1. **主诉 / Hero** — total score, grade band as a diagnosis line (e.g. "确诊：记忆虚胖症 · 伴 N% 上下文失联"), a one-line diagnosis, and the shock stats (total size, per-session token tax, % never loaded). The big title must stay readable — do not let it compress into an awkward multi-line block.
2. **两类记忆记分** — the four surface scores under 预置 / 外部.
3. **四维诊断（分数即证据）** — each dimension's score with its cited lines beneath it.
4. **矛盾专区** — the paired contradictions, diff-style with line numbers.
5. **处方笺** — 西药 (mechanical / high-confidence) and 中药 (judgment / medium-low confidence), each item with 剂量 (how many), 置信度, and expected 疗效 (+X). Word the 中药 items as recommendations to review, not as orders.
6. **疗效预测** — before/after: total, token tax, whether full loading is restored.

## Prescription → confirmation handoff

The prescription is not the end. Its items become the rows of the ReviewTable (治疗确认书). End the report with a clear path into that confirmation step, and do not apply any edit before the user has confirmed. See `references/review-table.md`.

## Producing the file

Populate `assets/diagnosis-template.html` with the scan's real numbers and evidence and write it to a working location the user can open (a scratch dir or the project). Keep it a single self-contained HTML — inline CSS/JS, no external requests, so it opens offline. Confirm every section is filled from real data and the contradiction pairs cite actual conflicting lines before handing it over.
