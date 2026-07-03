---
name: meta-learning
description: |
  Use when a correction, mistake, pitfall, failed workflow, example, or piece of feedback should become a durable update to a skill or agent instructions — e.g. "记录这个坑/教训到 skill", "把这次经验写进源码", "更新 skill 加上这条", "从这次失败里总结", "record this gotcha", "document this lesson", "learn from this and update the skill".
  Performs semantic skill refactoring: extract the transferable behavior and rewrite the owning skill so it reads clearer, instead of appending raw notes; also decides when NOT to add a reference file. Not for routine skill edits that carry no lesson.
---

# Meta Learning

Use this skill when "learning" means changing future agent behavior, not merely summarizing a source.

## Goal

The best learning makes the owning skill clearer, lower-noise, and easier to execute. A good update changes the decision structure an agent will follow next time: a routing table, state machine, checklist, trigger rule, negative example, or sharper workflow. It is not a scrapbook of the source material.

## Workflow

1. **Name the future behavior**: what should the next agent do differently?
2. **Find the owning skill**: update an existing skill when the lesson fits its domain. Create a new skill only when the behavior is reusable across domains or no owner exists.
3. **Diagnose the weak decision point**: ask what made the old behavior ambiguous. Typical fixes are "where to route this request", "when to escalate tools", "what not to create", or "what must be verified".
4. **Refactor, do not append**: rewrite the relevant section so the skill reads as a better operating guide. Merge sections that describe the same decision; remove or compress older text that the new structure replaces.
5. **Keep the surface minimal**: a few sentences belong in `SKILL.md`; a new reference file is justified only when the detail is optional, long, variant-specific, or too bulky for the main skill.
6. **Verify the learning**: check for dangling links, private facts, hardcoded local paths, line-count drift, and whether plugin README/manifests need updates.

## Patterns

- **Low-information source**: extract one principle or 2-3 examples; do not mirror the source outline.
- **Tool/source choice lesson**: prefer a routing table over prose because it makes execution explicit.
- **User correction**: update the trigger or anti-pattern that allowed the mistake, then simplify nearby text.
- **Site-specific mechanics**: keep login/browser details in the operational skill; only split to references when the steps are too long for the main document.
- **Terminology**: use domain-native words. Do not invent vague jargon, especially mixed English labels, unless the ecosystem already uses them.

## Anti-Patterns

- Keeping two sections that describe one decision because they came from different notes.
- Creating a new reference file because a source had headings.
- Copying a report's taxonomy when a single rule would change behavior.
- Adding project-private names, paths, cases, clients, or environment assumptions to a public skill.
