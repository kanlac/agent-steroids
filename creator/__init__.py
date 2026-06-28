"""Hermes plugin shim for the Agent Steroids creator plugin.

Hermes installs this repository as one git checkout, then discovers these
root-level shim directories as category-namespaced plugins such as
``agent-steroids/creator``.  The canonical cross-runtime skills stay under
``plugins/creator/skills`` for Claude Code and Codex compatibility.
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover - PyYAML ships with Hermes; defensive fallback.
    yaml = None

_VALID_SKILL = re.compile(r"^[A-Za-z0-9_-]+$")


def _frontmatter_description(skill_md: Path) -> str:
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end == -1:
        return ""
    frontmatter = text[3:end]
    if yaml is not None:
        try:
            data = yaml.safe_load(frontmatter) or {}
            value = data.get("description", "")
            return str(value).strip() if value is not None else ""
        except Exception:
            pass
    for line in frontmatter.splitlines():
        if line.strip().startswith("description:"):
            value = line.split(":", 1)[1].strip()
            return value.strip('"\'')
    return ""


def register(ctx) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    skills_dir = repo_root / "plugins" / "creator" / "skills"
    if not skills_dir.exists():
        return

    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skill_name = skill_md.parent.name
        if not _VALID_SKILL.match(skill_name):
            continue
        ctx.register_skill(
            skill_name,
            skill_md,
            description=_frontmatter_description(skill_md),
        )
