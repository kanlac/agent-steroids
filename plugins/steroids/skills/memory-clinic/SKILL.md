---
name: memory-clinic
description: |
  Audit, score, and clean up an agent's memory environment — the always-loaded instruction files (global and project CLAUDE.md / AGENTS.md) and the on-demand layer (skills, docs). Use whenever the user wants to check, grade, diagnose, declutter, prune, or health-check their agent memory / CLAUDE.md / skills, asks "is my CLAUDE.md too big / any good", says memory feels bloated or the agent ignores instructions, or asks where a lesson should live. Produces a "memory health" diagnosis report (HTML) plus an interactive confirmation table (ReviewTable) that captures which fixes to apply before the agent executes them. Trigger this even when the user just says "整理一下记忆 / 给我的 CLAUDE.md 打个分 / 记忆体检" without naming the skill.
---

# Memory Clinic

The clinic for an agent's memory. It holds the taste for **where each piece of memory should live**, turns that taste into a **scored diagnosis**, and closes the loop with a **human-confirmed cleanup**.

Diagnose → confirm → treat. Never silently rewrite a user's memory.

## The one idea: push vs pull

An agent's memory splits into two layers with opposite failure modes. Everything this skill does hangs off this distinction.

- **预置记忆 (push / preset)** — loaded into context *every* session: global `~/.claude/CLAUDE.md`, project `CLAUDE.md` / `AGENTS.md`, native auto-memory. Failure mode is **bloat**: every line taxes every turn, and past the budget the harness silently truncates it, so the agent gets *dumber*, not smarter. Push must be scarce.
- **外部记忆 (pull / external)** — retrieved only when needed: skill bodies, docs. It can grow, but it **rots, drifts, and contradicts itself**. Pull must stay findable and honest.

The core routing question for any lesson: *does it belong in push, in pull, in a skill as an improvement, or nowhere (git already has it)?* The full taste lives in `references/memory-philosophy.md` — read it before making judgment calls about what to keep, move, or cut.

## What the clinic does

Three jobs, always in this order:

1. **诊断 Diagnose** — scan the memory environment, score it, produce the diagnosis report.
2. **确认 Confirm** — hand the user a ReviewTable ("治疗确认书") so they decide, row by row, what actually gets changed.
3. **治疗 Treat** — read the saved confirmation and apply only the approved edits.

### Scope of a scan

Read everything the current environment exposes:

- Global memory: `~/.claude/CLAUDE.md` (and `~/.claude/AGENTS.md` if present)
- Project memory: `CLAUDE.md` / `AGENTS.md` at the repo root
- The pull layer that is reachable: installed/project skills and their descriptions, and any docs the instruction files point to

Do **not** wander into other projects' memory. The scan is about *this* agent, here.

## The four diagnostic dimensions

Each dimension answers one distinct question and must be **backed by evidence** — every deduction points to a concrete `file:line` and quotes it. No evidence, no points; a score with no receipts reads as a template and no one trusts it.

| 维度 | 它问的 | 典型信号 |
|---|---|---|
| **① 体量 Bloat** | 太臃肿吗? | 单文件 >200 行、总大小、每轮 token 税、大到被静默截断 |
| **② 可用性 Usability** | 有用且说得清吗? | 不改变任何决策的通用废话、模型能从 repo 推断的内容、含糊到无法执行的指令 |
| **③ 新鲜度 Freshness** | 过时了吗? | 指向已删/改名文件的断链、已完工的进度记录、失效的时效声明 |
| **④ 矛盾 Contradiction** | 自相打架吗? | 跨预置/外部：全局规则与某 skill、两个文档之间的冲突（成对呈现，带行号） |

Scores roll up by surface (global / project / skills / docs), then into a push score and a pull score weighted **5:5**, then a total 0–100 with a grade band. The score is a **directional reference, not a precise measure** — say so in the report. The scoring rubric, grade bands, and report generation live in `references/diagnosis-report.md`.

## Prescription: two kinds of fix, with confidence

Cleanup actions come in two flavors, and the split is the whole point of the confirm step:

- **💊 西药 (mechanical, high-confidence)** — deterministic fixes safe to apply directly: delete a finished-work record git already has, split a 260-line file, collapse a project file to `@AGENTS.md`.
- **🌿 中药 (judgment, medium/low-confidence)** — semantic calls that benefit from a human look: which contradicting rule wins, whether a lesson should be PR'd into a specific skill, whether a "temporary" note is truly dead. Present these as a recommendation with reasoning, not an order — the user is signing off, not being told.

## Confirm before treating (ReviewTable)

Diagnosis is not permission. After the report, hand the user an interactive **治疗确认书** (a ReviewTable): one row per prescription item, showing the finding, evidence, the agent's suggested action, and a confidence flag; the user checks what to apply, and for contradictions writes which side wins. Saving it writes a small JSON to disk; the agent reads that back and applies only the approved edits. This is what keeps the clinic from ever silently rewriting someone's memory. The interaction contract, JSON schema, and template live in `references/review-table.md`.

## Workflow

1. Read `references/memory-philosophy.md` for the routing taste, then scan the in-scope surfaces above.
2. Score the four dimensions with evidence, following `references/diagnosis-report.md`; render the diagnosis report from `assets/diagnosis-template.html`.
3. Generate the ReviewTable from `assets/review-table-template.html` per `references/review-table.md`, and point the user to it.
4. When the user says they've saved their choices, read the confirmation JSON and apply only the approved fixes — 西药 directly, 中药 as the user decided.
5. Re-state the resulting health delta (what the score would become) so the loop closes on a visible improvement.

## Notes

- This skill decides *where memory should live* and *whether it should exist at all* — it does not impose a specific wiki/doc structure, since every repo organizes docs differently.
- Related: `meta-learning` owns the deeper craft of rewriting a lesson *into* a skill (refactor, don't append). When a 中药 fix is "PR this into skill X", that is `meta-learning` territory.
