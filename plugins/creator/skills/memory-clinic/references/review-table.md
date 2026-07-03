# ReviewTable — the 治疗确认书 (treatment confirmation)

Diagnosis is not permission to edit. Between the report and any change stands a confirmation the user fills in themselves. The pattern is a **ReviewTable**: an interactive table where the agent lays out its findings and proposed actions, the user reviews and decides row by row, and the result is saved as a small JSON the agent reads back. It keeps the clinic from ever silently rewriting someone's memory.

The demo frames it as a "治疗确认书 / 知情同意书" — you sign off on which treatments to apply. The template is `assets/review-table-template.html`.

## Shape

One row per prescription item from the report. Columns:

- **病灶 / finding** — the problem, in plain terms.
- **证据 evidence** — the `file:line` and quoted text (same receipts as the report).
- **建议 action** — what the agent proposes to do (delete / split / move into skill X / reconcile / import).
- **置信度 confidence** — 高 / 中 / 低. High = mechanical, safe to apply as-is. Medium/low = a judgment call; visually flag these so the eye lands on the rows that most benefit from a look. Word them as "worth a look", never as a demand.
- **决定 decision** — the only user-owned column: apply / skip, and a free-text note. For a contradiction row, the note is where the user says which side wins.

Rows default to the sensible action (高置信 default to apply, 中低 default to review), but nothing is applied until the user saves and returns.

## Live prognosis

The predicted health score reacts to the checkboxes: as the user toggles rows on/off, recompute the projected total from each item's 疗效 (+X) and update it live in the page. It turns confirmation into a visible negotiation — "if I skip this, I stay at 61" — instead of a static form.

## Save → read-back contract

Saving writes a JSON the agent can read. For an offline single-file page, export via a download (Blob) to a known path — Downloads is fine for a demo — and the user tells the agent where it landed (or says "我填好了" and the agent looks in the default location). Schema:

```json
{
  "schema": "memory-clinic.review-table.v1",
  "generated_at": "<ISO8601>",
  "source_report": "<path or id of the diagnosis>",
  "projected_score": 84,
  "decisions": [
    {
      "id": "rx-001",
      "finding": "guard-payload-size 临时方案段已过期",
      "evidence": "agent-steroids/CLAUDE.md:88",
      "action": "delete",
      "confidence": "high",
      "apply": true,
      "note": ""
    },
    {
      "id": "rx-007",
      "finding": "yyMMdd vs YYYYMMDD 命名矛盾",
      "evidence": "~/.claude/CLAUDE.md ⚔ agent-steroids/CLAUDE.md",
      "action": "reconcile-naming",
      "confidence": "medium",
      "apply": true,
      "note": "统一用 YYYYMMDD"
    }
  ]
}
```

Keep field names stable (`id`, `action`, `apply`, `note`) — the treat step keys off them. `id` must match the prescription item ids the report/table assigned, so a decision maps back to a concrete edit.

## Treat

When the user returns, read the JSON and apply only rows with `apply: true`:

- **高置信 / mechanical** — apply directly.
- **中低置信 / judgment** — apply as the `note` directs; for a contradiction, edit toward the side the user chose. If a "PR into skill X" item is approved, that rewrite is `meta-learning`'s job — hand it there rather than stapling a raw note.

Then re-state the achieved delta (old score → new) so the loop closes on a visible win. Never apply a row the user left unchecked, and never edit beyond what a decision authorizes.
