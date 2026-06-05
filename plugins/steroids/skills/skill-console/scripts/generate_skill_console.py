#!/usr/bin/env python3
"""Generate a self-contained Skill inventory dashboard."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]


FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)
SKIP_PARTS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
}


def load_token_encoder(name: str):
    try:
        import tiktoken

        try:
            return tiktoken.get_encoding(name), f"tiktoken:{name}"
        except Exception:
            return tiktoken.get_encoding("o200k_base"), "tiktoken:o200k_base"
    except Exception:
        return None, "heuristic"


def token_count(text: str, encoder: Any) -> int:
    if not text:
        return 0
    if encoder is not None:
        return len(encoder.encode(text))
    # Conservative fallback when tiktoken is not installed.
    latin_words = re.findall(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", text)
    cjk_chars = re.findall(r"[\u3400-\u9fff]", text)
    return max(1, len(latin_words) + len(cjk_chars))


def parse_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.strip()


def parse_frontmatter(content: str) -> tuple[dict[str, str], str, str]:
    match = FRONTMATTER_RE.match(content)
    if not match:
        return {}, "", content

    raw = match.group(1)
    body = content[match.end() :]
    data: dict[str, str] = {}
    lines = raw.splitlines()
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        idx += 1
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        if line[:1].isspace():
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.rstrip()
        stripped = value.strip()
        if stripped in {"|", ">"}:
            collected: list[str] = []
            while idx < len(lines):
                nxt = lines[idx]
                if nxt and not nxt[:1].isspace() and ":" in nxt:
                    break
                collected.append(nxt.strip())
                idx += 1
            data[key] = "\n".join(collected).strip()
            continue
        if stripped == "":
            collected = []
            while idx < len(lines):
                nxt = lines[idx]
                if nxt and not nxt[:1].isspace() and ":" in nxt:
                    break
                collected.append(nxt.strip())
                idx += 1
            data[key] = " ".join(item for item in collected if item).strip()
            continue
        data[key] = parse_scalar(stripped)
    return data, raw, body


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_toml(path: Path) -> Any:
    if tomllib is None:
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def display_path(path: Path, project_root: Path, home: Path) -> str:
    if path.resolve() == project_root.resolve():
        return "."
    try:
        return "./" + path.relative_to(project_root).as_posix()
    except ValueError:
        pass
    try:
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return path.as_posix()


def shell_path(path: Path, project_root: Path, home: Path) -> str:
    try:
        return "./" + path.relative_to(project_root).as_posix()
    except ValueError:
        pass
    try:
        return "$HOME/" + path.relative_to(home).as_posix()
    except ValueError:
        return path.as_posix()


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def infer_plugin_id(path: Path, plugin_cache: Path) -> str:
    try:
        parts = path.relative_to(plugin_cache).parts
    except ValueError:
        return ""
    if len(parts) < 4:
        return ""
    marketplace, plugin = parts[0], parts[1]
    return f"{plugin}@{marketplace}"


def infer_scope(path: Path, project_root: Path, home: Path) -> str:
    project_prefixes = [
        project_root / ".claude" / "skills",
        project_root / ".agents" / "skills",
        project_root / ".codex" / "skills",
    ]
    for prefix in project_prefixes:
        if under(path, prefix):
            return "workspace"

    system_root = home / ".codex" / "skills" / ".system"
    if under(path, system_root):
        return "system"

    user_prefixes = [
        home / ".claude" / "skills",
        home / ".agents" / "skills",
        home / ".codex" / "skills",
    ]
    for prefix in user_prefixes:
        if under(path, prefix):
            return "user"

    if under(path, home / ".codex" / "plugins" / "cache"):
        return "plugin"

    return "other"


def root_label(path: Path, project_root: Path, home: Path) -> str:
    candidates = [
        (project_root / ".claude" / "skills", "workspace .claude"),
        (project_root / ".agents" / "skills", "workspace .agents"),
        (project_root / ".codex" / "skills", "workspace .codex"),
        (home / ".codex" / "skills" / ".system", "codex system"),
        (home / ".claude" / "skills", "user .claude"),
        (home / ".agents" / "skills", "user .agents"),
        (home / ".codex" / "skills", "user .codex"),
        (home / ".codex" / "plugins" / "cache", "plugin cache"),
    ]
    for prefix, label in candidates:
        if under(path, prefix):
            return label
    return "other"


def collect_skill_files(project_root: Path, home: Path) -> list[Path]:
    roots = [
        project_root / ".claude" / "skills",
        project_root / ".agents" / "skills",
        project_root / ".codex" / "skills",
        home / ".claude" / "skills",
        home / ".agents" / "skills",
        home / ".codex" / "skills",
        home / ".codex" / "plugins" / "cache",
    ]
    seen: set[Path] = set()
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("SKILL.md"):
            if any(part in SKIP_PARTS or part.endswith(".disabled") for part in path.parts):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)
    return sorted(files, key=lambda item: item.as_posix())


def plugin_enabled_maps(home: Path) -> tuple[dict[str, bool], dict[str, bool]]:
    codex: dict[str, bool] = {}
    claude: dict[str, bool] = {}

    codex_config = read_toml(home / ".codex" / "config.toml") or {}
    for plugin_id, config in (codex_config.get("plugins") or {}).items():
        if isinstance(config, dict) and "enabled" in config:
            codex[plugin_id] = bool(config["enabled"])

    claude_settings = read_json(home / ".claude" / "settings.json") or {}
    for plugin_id, enabled in (claude_settings.get("enabledPlugins") or {}).items():
        claude[plugin_id] = bool(enabled)
    return codex, claude


def load_lock(project_root: Path) -> dict[str, dict[str, Any]]:
    data = read_json(project_root / "skills-lock.json") or {}
    skills = data.get("skills")
    return skills if isinstance(skills, dict) else {}


def action_type(scope: str, plugin_id: str) -> str:
    if scope in {"workspace", "user"}:
        return "move"
    if scope == "plugin" and plugin_id:
        return "plugin"
    if scope == "system":
        return "keep"
    return "review"


def recommendation(scope: str, name: str, plugin_id: str, total_tokens: int, desc_tokens: int) -> str:
    if scope == "system":
        return "keep"
    if name in {
        "skill-creator",
        "skill-installer",
        "plugin-creator",
        "openai-docs",
        "control-in-app-browser",
        "cdp-chrome",
        "control-chrome",
    }:
        return "keep"
    if scope == "plugin" and plugin_id.startswith(("investment-banking@", "public-equity-investing@", "sales@", "creative-production@")):
        return "optional"
    if name.startswith("lark-") and name not in {"lark-shared", "lark-contact", "lark-im", "lark-doc", "lark-base"}:
        return "review"
    if desc_tokens >= 80 or total_tokens >= 1500:
        return "heavy"
    return "normal"


def build_inventory(project_root: Path, encoding_name: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    home = Path.home()
    encoder, tokenizer_label = load_token_encoder(encoding_name)
    codex_plugins, claude_plugins = plugin_enabled_maps(home)
    lock = load_lock(project_root)
    plugin_cache = home / ".codex" / "plugins" / "cache"
    rows: list[dict[str, Any]] = []

    for skill_file in collect_skill_files(project_root, home):
        try:
            content = skill_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = skill_file.read_text(encoding="utf-8", errors="replace")
        frontmatter, raw_frontmatter, body = parse_frontmatter(content)
        name = frontmatter.get("name") or skill_file.parent.name
        description = frontmatter.get("description", "")
        scope = infer_scope(skill_file, project_root, home)
        plugin_id = infer_plugin_id(skill_file, plugin_cache) if scope == "plugin" else ""

        if scope == "plugin" and plugin_id:
            codex_state = codex_plugins.get(plugin_id)
            claude_state = claude_plugins.get(plugin_id)
            enabled_sources = [
                label
                for label, state in (("codex", codex_state), ("claude", claude_state))
                if state is True
            ]
            disabled_sources = [
                label
                for label, state in (("codex", codex_state), ("claude", claude_state))
                if state is False
            ]
            if enabled_sources:
                status = "enabled plugin"
            elif disabled_sources:
                status = "disabled plugin"
            else:
                status = "cached plugin"
        elif scope == "system":
            status = "system"
        elif scope in {"workspace", "user"}:
            status = "local"
        else:
            status = "found"

        total_tokens = token_count(content, encoder)
        description_tokens = token_count(description, encoder)
        body_tokens = token_count(body, encoder)
        content_lines = content.splitlines()
        preview_lines = content_lines[:200]
        skill_dir = skill_file.parent
        skill_md_path = display_path(skill_file, project_root, home)
        skill_dir_path = display_path(skill_dir, project_root, home)
        prompt_line = f"- {name}: {description} (file: {skill_md_path})"
        prompt_tokens = token_count(prompt_line, encoder)
        locked = lock.get(name, {})

        rows.append(
            {
                "id": f"{skill_dir_path}::{name}",
                "name": name,
                "description": description,
                "scope": scope,
                "source": root_label(skill_file, project_root, home),
                "status": status,
                "pluginId": plugin_id,
                "codexPluginEnabled": codex_plugins.get(plugin_id) if plugin_id else None,
                "claudePluginEnabled": claude_plugins.get(plugin_id) if plugin_id else None,
                "path": skill_dir_path,
                "skillMdPath": skill_md_path,
                "dir": skill_dir_path,
                "shellPath": shell_path(skill_dir, project_root, home),
                "totalTokens": total_tokens,
                "descriptionTokens": description_tokens,
                "bodyTokens": body_tokens,
                "frontmatterTokens": token_count(raw_frontmatter, encoder),
                "promptTokens": prompt_tokens,
                "lines": len(content_lines),
                "previewText": "\n".join(preview_lines),
                "previewLineCount": len(preview_lines),
                "previewTotalLines": len(content_lines),
                "previewTruncated": len(content_lines) > len(preview_lines),
                "bytes": len(content.encode("utf-8")),
                "lockSource": locked.get("source", ""),
                "lockSourceType": locked.get("sourceType", ""),
                "actionType": action_type(scope, plugin_id),
                "recommendation": recommendation(scope, name, plugin_id, total_tokens, description_tokens),
            }
        )

    counts_by_name: dict[str, int] = {}
    for row in rows:
        counts_by_name[row["name"]] = counts_by_name.get(row["name"], 0) + 1

    duplicates_by_name: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if counts_by_name[row["name"]] < 2:
            continue
        duplicates_by_name.setdefault(row["name"], []).append(
            {
                "path": row["path"],
                "skillMdPath": row["skillMdPath"],
                "scope": row["scope"],
                "source": row["source"],
                "status": row["status"],
                "pluginId": row["pluginId"],
            }
        )

    for row in rows:
        row["duplicateCount"] = counts_by_name[row["name"]]
        row["duplicateLocations"] = duplicates_by_name.get(row["name"], [])

    active_rows = [
        row
        for row in rows
        if row["status"] in {"local", "system", "enabled plugin"}
    ]
    meta = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "projectRoot": display_path(project_root, project_root, home),
        "tokenizer": tokenizer_label,
        "skillCount": len(rows),
        "activeSkillCount": len(active_rows),
        "totalSkillTokens": sum(row["totalTokens"] for row in rows),
        "activeSkillTokens": sum(row["totalTokens"] for row in active_rows),
        "totalDescriptionTokens": sum(row["descriptionTokens"] for row in rows),
        "activeDescriptionTokens": sum(row["descriptionTokens"] for row in active_rows),
        "totalPromptTokens": sum(row["promptTokens"] for row in rows),
        "activePromptTokens": sum(row["promptTokens"] for row in active_rows),
    }
    return rows, meta


def render_html(rows: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    payload = json.dumps({"meta": meta, "skills": rows}, ensure_ascii=False)
    generated = html.escape(str(meta["generatedAt"]))
    tokenizer = html.escape(str(meta["tokenizer"]))
    return HTML_TEMPLATE.replace("__PAYLOAD__", payload).replace("__GENERATED__", generated).replace("__TOKENIZER__", tokenizer)


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Skill Console</title>
  <style>
    :root {
      --ink: #151816;
      --muted: #5c645f;
      --faint: #8a938c;
      --line: #d8ddd7;
      --line-strong: #b9c1ba;
      --paper: #f8f8f4;
      --panel: #ffffff;
      --panel-alt: #f0f3ee;
      --accent: #0f766e;
      --accent-2: #b42318;
      --accent-3: #7a4b00;
      --shadow: 0 18px 42px rgba(21, 24, 22, 0.08);
      --radius: 6px;
      color-scheme: light;
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      background:
        linear-gradient(90deg, rgba(15, 118, 110, 0.06) 1px, transparent 1px),
        linear-gradient(180deg, rgba(15, 118, 110, 0.05) 1px, transparent 1px),
        var(--paper);
      background-size: 32px 32px;
      color: var(--ink);
      letter-spacing: 0;
    }

    header {
      display: grid;
      grid-template-columns: minmax(260px, 1fr) auto;
      gap: 24px;
      align-items: end;
      padding: 26px 28px 18px;
      border-bottom: 1px solid var(--line);
      background: rgba(248, 248, 244, 0.94);
      backdrop-filter: blur(14px);
      position: sticky;
      top: 0;
      z-index: 20;
    }

    h1 {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(28px, 4vw, 46px);
      font-weight: 700;
      line-height: 0.98;
    }

    .meta {
      color: var(--muted);
      font-size: 13px;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    main { padding: 18px 28px 28px; }

    .metrics {
      display: grid;
      grid-template-columns: repeat(6, minmax(120px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }

    .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 12px 12px 10px;
      box-shadow: var(--shadow);
      min-width: 0;
    }

    .metric b {
      display: block;
      font-size: 22px;
      line-height: 1.05;
      font-variant-numeric: tabular-nums;
      overflow-wrap: anywhere;
    }

    .metric span {
      display: block;
      margin-top: 7px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .controls {
      display: grid;
      grid-template-columns: minmax(220px, 1.2fr) repeat(5, minmax(130px, 1fr));
      gap: 10px;
      align-items: end;
      background: rgba(255, 255, 255, 0.88);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 12px;
      box-shadow: var(--shadow);
      margin-bottom: 14px;
    }

    label {
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
      min-width: 0;
    }

    input, select, button, textarea {
      font: inherit;
      letter-spacing: 0;
    }

    input, select {
      width: 100%;
      border: 1px solid var(--line-strong);
      border-radius: 5px;
      background: #fff;
      color: var(--ink);
      padding: 9px 10px;
      min-height: 38px;
      outline: none;
    }

    input:focus, select:focus, textarea:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.14);
    }

    .toggle-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 14px;
    }

    .toggle {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 5px;
      padding: 7px 10px;
      color: var(--muted);
      font-size: 13px;
    }

    .toggle input {
      width: 15px;
      height: 15px;
      min-height: auto;
      margin: 0;
      accent-color: var(--accent);
    }

    .row-check {
      width: 18px;
      height: 18px;
      min-height: auto;
      margin: 2px 0 0;
      accent-color: var(--accent);
    }

    .workbench {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 390px;
      gap: 14px;
      align-items: start;
    }

    .table-wrap {
      overflow: auto;
      max-height: calc(100vh - 280px);
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      min-width: 2800px;
      font-size: 13px;
    }

    col.select-col { width: 54px; }
    col.skill-col { width: 238px; }
    col.description-col { width: 640px; }
    col.token-col { width: 82px; }
    col.line-col { width: 72px; }
    col.scope-col { width: 92px; }
    col.status-col { width: 132px; }
    col.tag-col { width: 100px; }
    col.duplicate-col { width: 520px; }
    col.plugin-col { width: 236px; }
    col.path-col { width: 322px; }

    thead th {
      position: sticky;
      top: 0;
      z-index: 5;
      background: #edf1ec;
      color: #2f3732;
      text-align: left;
      border-bottom: 1px solid var(--line-strong);
      padding: 9px 8px;
      white-space: nowrap;
      font-weight: 700;
      cursor: pointer;
      user-select: none;
    }

    tbody td {
      border-bottom: 1px solid var(--line);
      padding: 8px;
      vertical-align: top;
    }

    tbody tr:hover { background: #f7faf6; }

    .num {
      text-align: right;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }

    .mono {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }

    .truncate {
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .path {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      color: #33413a;
      white-space: normal;
      overflow-wrap: anywhere;
    }

    .plugin-cell {
      white-space: normal;
      overflow-wrap: anywhere;
    }

    .desc {
      color: var(--muted);
      line-height: 1.48;
      white-space: normal;
      overflow-wrap: anywhere;
    }

    .desc-text {
      display: block;
      white-space: normal;
      overflow: visible;
    }

    .duplicate-cell {
      color: var(--muted);
      line-height: 1.42;
      overflow-wrap: anywhere;
    }

    .duplicate-list {
      display: grid;
      gap: 6px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .duplicate-path {
      display: block;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      color: #27332d;
    }

    .duplicate-meta {
      display: block;
      margin-top: 2px;
      color: var(--faint);
      font-size: 12px;
    }

    .desc-duplicates {
      margin-top: 10px;
      padding-top: 8px;
      border-top: 1px dashed var(--line-strong);
      color: #27332d;
    }

    .desc-duplicates b {
      display: block;
      margin-bottom: 6px;
      color: var(--accent-2);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
    }

    .empty {
      color: var(--faint);
    }

    .skill-meta {
      display: block;
      margin-top: 5px;
      color: var(--faint);
      line-height: 1.35;
    }

    .compact {
      color: var(--muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .name {
      appearance: none;
      border: 0;
      background: transparent;
      padding: 0;
      margin: 0;
      text-align: left;
      font: inherit;
      font-weight: 700;
      color: var(--ink);
      white-space: nowrap;
      cursor: pointer;
    }

    .name:hover {
      color: var(--accent);
      text-decoration: underline;
      text-underline-offset: 3px;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line-strong);
      border-radius: 999px;
      padding: 2px 8px;
      color: #36403a;
      background: #fff;
      font-size: 12px;
      white-space: nowrap;
    }

    .badge.heavy, .badge.optional { border-color: #e6c56c; background: #fff7df; color: var(--accent-3); }
    .badge.keep { border-color: #9bc8c3; background: #e7f5f3; color: #0b5d56; }
    .badge.review { border-color: #efb4ad; background: #fff0ee; color: var(--accent-2); }

    aside {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 12px;
      position: sticky;
      top: 145px;
    }

    aside h2 {
      margin: 0 0 10px;
      font-size: 15px;
      line-height: 1.2;
    }

    .selected-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-bottom: 10px;
    }

    .selected-grid div {
      border: 1px solid var(--line);
      border-radius: 5px;
      padding: 8px;
      background: var(--panel-alt);
    }

    .selected-grid b {
      display: block;
      font-variant-numeric: tabular-nums;
    }

    .selected-grid span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-top: 4px;
    }

    textarea {
      width: 100%;
      min-height: 310px;
      resize: vertical;
      border: 1px solid var(--line-strong);
      border-radius: 5px;
      padding: 10px;
      background: #fbfcfa;
      color: #18221c;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
    }

    .output-mode {
      margin: 10px 0 8px;
    }

    .button-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 8px;
    }

    .button-row .wide {
      grid-column: 1 / -1;
    }

    button {
      border: 1px solid var(--line-strong);
      border-radius: 5px;
      padding: 9px 10px;
      background: #fff;
      color: var(--ink);
      cursor: pointer;
      min-height: 38px;
    }

    button:hover { border-color: var(--accent); color: var(--accent); }
    button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    button.primary:hover { background: #0b5d56; color: #fff; }

    .bar {
      height: 8px;
      border-radius: 999px;
      background: #dfe4de;
      overflow: hidden;
      margin: 9px 0 12px;
    }

    .bar span {
      display: block;
      height: 100%;
      width: 0%;
      background: var(--accent);
    }

    .bar.over span { background: var(--accent-2); }

    .small {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }

    .modal-backdrop {
      position: fixed;
      inset: 0;
      z-index: 100;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 22px;
      background: rgba(21, 24, 22, 0.42);
      backdrop-filter: blur(6px);
    }

    .modal-backdrop.open {
      display: flex;
    }

    .modal {
      width: min(1120px, calc(100vw - 36px));
      max-height: calc(100vh - 44px);
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      background: #fbfcfa;
      border: 1px solid var(--line-strong);
      border-radius: var(--radius);
      box-shadow: 0 26px 80px rgba(21, 24, 22, 0.28);
      overflow: hidden;
    }

    .modal-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      align-items: start;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      background: #eef2ed;
    }

    .modal-title {
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
    }

    .modal-meta {
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }

    .modal-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: end;
    }

    .modal-body {
      overflow: auto;
      padding: 0;
      background: #101511;
    }

    .skill-preview {
      margin: 0;
      min-height: 420px;
      padding: 16px 18px;
      color: #e8eee7;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.55;
      white-space: pre;
      tab-size: 2;
    }

    @media (max-width: 1180px) {
      header { grid-template-columns: 1fr; align-items: start; }
      .meta { justify-content: flex-start; }
      .metrics { grid-template-columns: repeat(3, minmax(120px, 1fr)); }
      .controls { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .workbench { grid-template-columns: 1fr; }
      aside { position: static; }
      .table-wrap { max-height: 68vh; }
    }

    @media (max-width: 700px) {
      header, main { padding-left: 14px; padding-right: 14px; }
      .metrics, .controls { grid-template-columns: 1fr; }
      h1 { font-size: 30px; }
      .modal-backdrop { padding: 10px; }
      .modal { width: calc(100vw - 20px); max-height: calc(100vh - 20px); }
      .modal-head { grid-template-columns: 1fr; }
      .modal-actions { justify-content: stretch; }
      .modal-actions button { flex: 1; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Skill Console</h1>
    </div>
    <div class="meta">
      <span>Generated: __GENERATED__</span>
      <span>Tokenizer: __TOKENIZER__</span>
    </div>
  </header>

  <main>
    <section class="metrics" aria-label="metrics">
      <div class="metric"><b id="metric-count">0</b><span>visible skills</span></div>
      <div class="metric"><b id="metric-active">0</b><span>active skills</span></div>
      <div class="metric"><b id="metric-desc">0</b><span>visible desc tokens</span></div>
      <div class="metric"><b id="metric-prompt">0</b><span>visible prompt tokens</span></div>
      <div class="metric"><b id="metric-total">0</b><span>visible SKILL.md tokens</span></div>
      <div class="metric"><b id="metric-over">0</b><span>over budget</span></div>
    </section>

    <section class="controls">
      <label>Search
        <input id="search" type="search" placeholder="name, description, path, plugin">
      </label>
      <label>Scope
        <select id="scope"></select>
      </label>
      <label>Status
        <select id="status"></select>
      </label>
      <label>Plugin
        <select id="plugin"></select>
      </label>
      <label>Sort
        <select id="sort">
          <option value="descriptionTokens">description tokens</option>
          <option value="promptTokens">prompt-line tokens</option>
          <option value="totalTokens">SKILL.md tokens</option>
          <option value="bodyTokens">body tokens</option>
          <option value="lines">lines</option>
          <option value="name">name</option>
        </select>
      </label>
      <label>Budget
        <input id="budget" type="number" min="0" step="500" value="12000">
      </label>
    </section>

    <section class="toggle-row">
      <label class="toggle"><input id="activeOnly" type="checkbox"> active only</label>
      <label class="toggle"><input id="duplicatesOnly" type="checkbox"> duplicates only</label>
      <label class="toggle"><input id="selectedOnly" type="checkbox"> selected only</label>
      <label class="toggle"><input id="descending" type="checkbox" checked> descending</label>
    </section>

    <section class="workbench">
      <div class="table-wrap">
        <table>
          <colgroup>
            <col class="select-col">
            <col class="skill-col">
            <col class="description-col">
            <col class="token-col">
            <col class="token-col">
            <col class="token-col">
            <col class="token-col">
            <col class="line-col">
                <col class="scope-col">
                <col class="status-col">
                <col class="tag-col">
                <col class="duplicate-col">
                <col class="plugin-col">
                <col class="path-col">
          </colgroup>
          <thead>
            <tr>
              <th data-sort="selected">Select</th>
              <th data-sort="name">Skill</th>
              <th>Description</th>
              <th data-sort="descriptionTokens" class="num">Desc</th>
              <th data-sort="promptTokens" class="num">Prompt</th>
              <th data-sort="totalTokens" class="num">Total</th>
              <th data-sort="bodyTokens" class="num">Body</th>
              <th data-sort="lines" class="num">Lines</th>
              <th data-sort="scope">Scope</th>
              <th data-sort="status">Status</th>
              <th data-sort="recommendation">Tag</th>
              <th data-sort="duplicateCount">Duplicate Skill dirs</th>
              <th data-sort="pluginId">Plugin</th>
              <th data-sort="path">Skill path</th>
            </tr>
          </thead>
          <tbody id="rows"></tbody>
        </table>
      </div>

      <aside>
        <h2>Selected impact</h2>
        <div class="selected-grid">
          <div><b id="selected-count">0</b><span>skills</span></div>
          <div><b id="selected-desc">0</b><span>desc tokens</span></div>
          <div><b id="selected-prompt">0</b><span>prompt tokens</span></div>
          <div><b id="selected-total">0</b><span>total tokens</span></div>
        </div>
        <div id="budget-bar" class="bar"><span></span></div>
        <label class="output-mode">Output
          <select id="outputMode">
            <option value="json" selected>JSON</option>
            <option value="plan">Plan</option>
          </select>
        </label>
        <textarea id="output" spellcheck="false"></textarea>
        <div class="button-row">
          <button id="selectVisible" type="button">Select visible</button>
          <button id="clearSelected" type="button">Clear</button>
          <button id="copyOutput" class="primary" type="button">Copy output</button>
          <button id="downloadJson" type="button">Download JSON</button>
          <button id="copyPaths" type="button">Copy skill paths</button>
        </div>
        <p class="small">Move commands are generated only for local Skill directories. Plugin rows produce config notes so the cache is not edited directly.</p>
      </aside>
    </section>
  </main>

  <div id="skillModalBackdrop" class="modal-backdrop" role="presentation">
    <section class="modal" role="dialog" aria-modal="true" aria-labelledby="skillModalTitle">
      <div class="modal-head">
        <div>
          <h2 id="skillModalTitle" class="modal-title">Skill Preview</h2>
          <div id="skillModalMeta" class="modal-meta"></div>
        </div>
        <div class="modal-actions">
          <button id="copyPreview" type="button">Copy preview</button>
          <button id="closePreview" class="primary" type="button">Close</button>
        </div>
      </div>
      <div class="modal-body">
        <pre id="skillPreview" class="skill-preview"></pre>
      </div>
    </section>
  </div>

  <script>
    const DATA = __PAYLOAD__;
    const skills = DATA.skills;
    const selected = new Set();
    let visible = [];

    const el = (id) => document.getElementById(id);
    const fmt = new Intl.NumberFormat("en-US");

    function isActive(row) {
      return row.status === "local" || row.status === "system" || row.status === "enabled plugin";
    }

    function uniqueValues(key, label) {
      const values = Array.from(new Set(skills.map((row) => row[key]).filter(Boolean))).sort();
      return [`<option value="">All ${label}</option>`, ...values.map((value) => `<option value="${escapeAttr(value)}">${escapeHtml(value)}</option>`)].join("");
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[char]));
    }

    function escapeAttr(value) {
      return escapeHtml(value).replace(/`/g, "&#96;");
    }

    function numberCell(value) {
      return `<td class="num">${fmt.format(value || 0)}</td>`;
    }

    function renderDuplicateLocations(row) {
      if (!row.duplicateLocations || row.duplicateLocations.length < 2) {
        return `<span class="empty">-</span>`;
      }
      const items = row.duplicateLocations.map((item) => {
        const plugin = item.pluginId ? ` · ${item.pluginId}` : "";
        return `<li><span class="duplicate-path">${escapeHtml(item.path)}</span><span class="duplicate-meta">${escapeHtml(item.scope)} · ${escapeHtml(item.status)} · ${escapeHtml(item.source)}${escapeHtml(plugin)}</span></li>`;
      }).join("");
      return `<ul class="duplicate-list">${items}</ul>`;
    }

    function numberedPreview(row) {
      const lines = String(row.previewText || "").split("\\n");
      return lines.map((line, index) => `${String(index + 1).padStart(3, " ")}  ${line}`).join("\\n");
    }

    function openSkillPreview(row) {
      el("skillModalTitle").textContent = row.name;
      const lineText = row.previewTruncated
        ? `showing first ${row.previewLineCount} of ${row.previewTotalLines} lines`
        : `showing all ${row.previewTotalLines} lines`;
      el("skillModalMeta").textContent = `${row.skillMdPath} · ${lineText} · desc ${fmt.format(row.descriptionTokens)} · total ${fmt.format(row.totalTokens)}`;
      el("skillPreview").textContent = numberedPreview(row);
      el("skillModalBackdrop").classList.add("open");
      el("closePreview").focus();
    }

    function closeSkillPreview() {
      el("skillModalBackdrop").classList.remove("open");
    }

    function matchesSearch(row, q) {
      if (!q) return true;
      const haystack = [
        row.name,
        row.description,
        row.path,
        row.skillMdPath,
        row.pluginId,
        row.source,
        row.status,
        row.recommendation
      ].join("\\n").toLowerCase();
      return haystack.includes(q);
    }

    function filteredRows() {
      const q = el("search").value.trim().toLowerCase();
      const scope = el("scope").value;
      const status = el("status").value;
      const plugin = el("plugin").value;
      return skills.filter((row) => {
        if (el("activeOnly").checked && !isActive(row)) return false;
        if (el("duplicatesOnly").checked && row.duplicateCount < 2) return false;
        if (el("selectedOnly").checked && !selected.has(row.id)) return false;
        if (scope && row.scope !== scope) return false;
        if (status && row.status !== status) return false;
        if (plugin && row.pluginId !== plugin) return false;
        return matchesSearch(row, q);
      });
    }

    function compareRows(a, b, key, descending) {
      const av = a[key];
      const bv = b[key];
      let result;
      if (typeof av === "number" && typeof bv === "number") {
        result = av - bv;
      } else if (key === "selected") {
        result = Number(selected.has(a.id)) - Number(selected.has(b.id));
      } else {
        result = String(av || "").localeCompare(String(bv || ""));
      }
      if (result === 0) {
        result = String(a.name).localeCompare(String(b.name));
      }
      return descending ? -result : result;
    }

    function renderRows() {
      const sortKey = el("sort").value;
      const desc = el("descending").checked;
      visible = filteredRows().sort((a, b) => compareRows(a, b, sortKey, desc));
      const html = visible.map((row) => {
        const checked = selected.has(row.id) ? " checked" : "";
        const dup = row.duplicateCount > 1 ? ` <span class="badge review">dup ${row.duplicateCount}</span>` : "";
        const plugin = row.pluginId || "-";
        const duplicateDetails = row.duplicateCount > 1 ? `<div class="desc-duplicates"><b>Duplicate Skill dirs</b>${renderDuplicateLocations(row)}</div>` : "";
        return `<tr>
          <td><input class="row-check" type="checkbox" data-id="${escapeAttr(row.id)}"${checked} aria-label="select ${escapeAttr(row.name)}"></td>
          <td><button class="name" type="button" data-preview-id="${escapeAttr(row.id)}">${escapeHtml(row.name)}</button>${dup}<span class="skill-meta">${escapeHtml(row.source)} · desc ${fmt.format(row.descriptionTokens)} · total ${fmt.format(row.totalTokens)}</span></td>
          <td class="desc" title="${escapeAttr(row.description)}"><span class="desc-text">${escapeHtml(row.description)}</span>${duplicateDetails}</td>
          ${numberCell(row.descriptionTokens)}
          ${numberCell(row.promptTokens)}
          ${numberCell(row.totalTokens)}
          ${numberCell(row.bodyTokens)}
          ${numberCell(row.lines)}
          <td class="compact">${escapeHtml(row.scope)}</td>
          <td class="compact">${escapeHtml(row.status)}</td>
          <td><span class="badge ${escapeAttr(row.recommendation)}">${escapeHtml(row.recommendation)}</span></td>
          <td class="duplicate-cell">${renderDuplicateLocations(row)}</td>
          <td><span class="mono plugin-cell">${escapeHtml(plugin)}</span></td>
          <td class="path" title="${escapeAttr(row.path)}">${escapeHtml(row.path)}</td>
        </tr>`;
      }).join("");
      el("rows").innerHTML = html || `<tr><td colspan="14">No matching skills.</td></tr>`;
      el("rows").querySelectorAll("input[type='checkbox']").forEach((box) => {
        box.addEventListener("change", (event) => {
          const id = event.currentTarget.dataset.id;
          if (event.currentTarget.checked) selected.add(id);
          else selected.delete(id);
          renderSummary();
        });
      });
      el("rows").querySelectorAll("[data-preview-id]").forEach((button) => {
        button.addEventListener("click", (event) => {
          const id = event.currentTarget.dataset.previewId;
          const row = skills.find((item) => item.id === id);
          if (row) openSkillPreview(row);
        });
      });
      renderSummary();
    }

    function sum(rows, key) {
      return rows.reduce((total, row) => total + (row[key] || 0), 0);
    }

    function selectedRows() {
      return skills.filter((row) => selected.has(row.id));
    }

    function renderSummary() {
      const activeVisible = visible.filter(isActive);
      const descTokens = sum(visible, "descriptionTokens");
      const promptTokens = sum(visible, "promptTokens");
      const totalTokens = sum(visible, "totalTokens");
      const budget = Number(el("budget").value || 0);
      const over = Math.max(0, descTokens - budget);
      el("metric-count").textContent = fmt.format(visible.length);
      el("metric-active").textContent = fmt.format(activeVisible.length);
      el("metric-desc").textContent = fmt.format(descTokens);
      el("metric-prompt").textContent = fmt.format(promptTokens);
      el("metric-total").textContent = fmt.format(totalTokens);
      el("metric-over").textContent = fmt.format(over);

      const sel = selectedRows();
      el("selected-count").textContent = fmt.format(sel.length);
      el("selected-desc").textContent = fmt.format(sum(sel, "descriptionTokens"));
      el("selected-prompt").textContent = fmt.format(sum(sel, "promptTokens"));
      el("selected-total").textContent = fmt.format(sum(sel, "totalTokens"));

      const pct = budget ? Math.min(100, Math.round((descTokens / budget) * 100)) : 0;
      const bar = el("budget-bar");
      bar.classList.toggle("over", over > 0);
      bar.querySelector("span").style.width = `${pct}%`;
      renderOutput(sel);
    }

    function planText(rows) {
      const moveRows = rows.filter((row) => row.actionType === "move");
      const pluginRows = rows.filter((row) => row.actionType === "plugin");
      const keepRows = rows.filter((row) => row.actionType === "keep");
      const lines = [];
      lines.push("# Review before running. Project-relative commands assume repo root.");
      lines.push(`# Selected: ${rows.length} skill(s), ${sum(rows, "descriptionTokens")} description tokens, ${sum(rows, "totalTokens")} total SKILL.md tokens.`);
      lines.push("");
      if (moveRows.length) {
        lines.push("# Local/user Skill directories");
        for (const row of moveRows) {
          const disabledDir = row.shellPath.replace(/\\/skills\\/([^/]+)$/, "/skills.disabled/$1");
          lines.push(`mkdir -p ${quoteShell(disabledDir.replace(/\\/[^/]+$/, ""))}`);
          lines.push(`mv ${quoteShell(row.shellPath)} ${quoteShell(disabledDir)}`);
        }
        lines.push("");
      }
      if (pluginRows.length) {
        lines.push("# Plugin-backed Skills");
        const groups = new Map();
        for (const row of pluginRows) {
          if (!groups.has(row.pluginId)) groups.set(row.pluginId, []);
          groups.get(row.pluginId).push(row.name);
        }
        for (const [pluginId, names] of groups) {
          lines.push(`# ${pluginId}: ${names.sort().join(", ")}`);
          lines.push(`# Set enabled = false for [plugins."${pluginId}"] in ~/.codex/config.toml, or set enabledPlugins["${pluginId}"] = false in ~/.claude/settings.json.`);
        }
        lines.push("");
      }
      if (keepRows.length) {
        lines.push("# Kept by default");
        for (const row of keepRows) lines.push(`# ${row.name}: ${row.path}`);
      }
      return lines.join("\\n");
    }

    function exportObject(rows) {
      return rows.map((row) => ({
        name: row.name,
        path: row.path
      }));
    }

    function jsonText(rows) {
      return JSON.stringify(exportObject(rows), null, 2);
    }

    function renderOutput(rows) {
      const mode = el("outputMode").value;
      el("output").value = mode === "json" ? jsonText(rows) : planText(rows);
    }

    function quoteShell(value) {
      return "'" + String(value).replace(/'/g, "'\\"'\\"'") + "'";
    }

    async function copyText(text) {
      try {
        await navigator.clipboard.writeText(text);
      } catch (_error) {
        const box = el("output");
        box.focus();
        box.select();
        document.execCommand("copy");
      }
    }

    function downloadJson() {
      const rows = selectedRows();
      const blob = new Blob([jsonText(rows)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `skill-selection-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }

    function setup() {
      el("scope").innerHTML = uniqueValues("scope", "scopes");
      el("status").innerHTML = uniqueValues("status", "statuses");
      el("plugin").innerHTML = uniqueValues("pluginId", "plugins");

      ["search", "scope", "status", "plugin", "sort", "budget"].forEach((id) => {
        el(id).addEventListener("input", renderRows);
        el(id).addEventListener("change", renderRows);
      });
      ["activeOnly", "duplicatesOnly", "selectedOnly", "descending"].forEach((id) => {
        el(id).addEventListener("change", renderRows);
      });
      el("outputMode").addEventListener("change", renderSummary);
      document.querySelectorAll("thead th[data-sort]").forEach((th) => {
        th.addEventListener("click", () => {
          const key = th.dataset.sort;
          if (key === "selected") {
            el("selectedOnly").checked = !el("selectedOnly").checked;
          } else if (el("sort").value === key) {
            el("descending").checked = !el("descending").checked;
          } else {
            el("sort").value = key;
            el("descending").checked = true;
          }
          renderRows();
        });
      });
      el("selectVisible").addEventListener("click", () => {
        visible.forEach((row) => selected.add(row.id));
        renderRows();
      });
      el("clearSelected").addEventListener("click", () => {
        selected.clear();
        renderRows();
      });
      el("copyOutput").addEventListener("click", () => copyText(el("output").value));
      el("downloadJson").addEventListener("click", downloadJson);
      el("closePreview").addEventListener("click", closeSkillPreview);
      el("copyPreview").addEventListener("click", () => copyText(el("skillPreview").textContent));
      el("skillModalBackdrop").addEventListener("click", (event) => {
        if (event.target === el("skillModalBackdrop")) closeSkillPreview();
      });
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && el("skillModalBackdrop").classList.contains("open")) {
          closeSkillPreview();
        }
      });
      el("copyPaths").addEventListener("click", () => {
        copyText(selectedRows().map((row) => row.path).join("\\n"));
      });
      renderRows();
    }

    setup();
  </script>
</body>
</html>
"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("skill-console.html"),
        help="HTML output path.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Workspace root to scan for project-local skills. Defaults to the current directory.",
    )
    parser.add_argument(
        "--encoding",
        default="o200k_base",
        help="tiktoken encoding name. Defaults to o200k_base.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    project_root = args.project_root.resolve()
    rows, meta = build_inventory(project_root, args.encoding)
    html_text = render_html(rows, meta)
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_text, encoding="utf-8")
    print(
        f"Wrote {output} with {meta['skillCount']} skills "
        f"({meta['activeDescriptionTokens']} active description tokens, {meta['tokenizer']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
