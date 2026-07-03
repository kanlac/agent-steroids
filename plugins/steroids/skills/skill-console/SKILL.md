---
name: skill-console
description: |
  Generate a local HTML dashboard for auditing installed Skills, token usage, description token budgets, duplicate Skill names, Skill paths, and selected Skill exports.
  Use when the user wants to inspect many Skills, decide which Skills to disable, compare duplicates, preview SKILL.md contents, sort by token usage, or export selected Skills as JSON.
---

# Skill Console

Use this skill when Skill inventory itself is the object of work: too many Skills are loaded, token budget is unclear, duplicate names need explanation, or the user wants to hand back a compact list of selected Skills.

## Dashboard

Generate the self-contained HTML page with the bundled script:

```bash
python3 "${SKILL_PATH}/scripts/generate_skill_console.py" --project-root "$PWD" --output skill-console.html
```

Open the resulting HTML locally and verify it visually when changing the page or when the user is relying on dense table columns. The dashboard is designed for:

- token sorting by description, prompt-line, body, total `SKILL.md`, and line count
- full description reading without clipping
- duplicate-name inspection with every duplicate Skill directory visible
- Skill title preview modals that show the first 200 lines of the backing `SKILL.md`
- selection export for sharing selected Skills back to an agent

## Export Contract

JSON export is intentionally minimal. It must be an array of selected Skills only:

```json
[
  {
    "name": "skill-name",
    "path": "~/.claude/skills/skill-name"
  }
]
```

`path` is always the Skill directory path, not the `SKILL.md` file path. Keep `SKILL.md` paths internal to preview and token accounting.

## Disable Decisions

Treat the dashboard as an audit and planning tool. For local user or workspace Skills, prefer moving whole Skill directories to a sibling `skills.disabled/` directory so the action is reversible. For plugin-backed Skills, prefer disabling the owning plugin in runtime config instead of editing plugin cache contents directly.

Only delete or move Skills after the user explicitly asks for that operation and the paths have been checked against the selected JSON or dashboard rows.

## Visual Rule

Dense Skill tables must define column priorities and widths before visual QA. Long fields such as description, duplicate paths, plugin IDs, and Skill paths need explicit wrapping or a details surface; do not depend on browser automatic table layout.
