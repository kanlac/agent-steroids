#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""taskdag — 仓库原生的 Task DAG + ADR 控制面。

单文件、仅 Python 标准库。此副本 vendor 在项目 `scripts/taskdag.py`；
canonical 源在 agent-steroids 的 taskdag 插件（skills/orchestrator/scripts/taskdag.py）。

约定（本项目如有偏差，改下方常量区，不改逻辑）：
- 任务文件 docs/tasks/T-*.md，ADR 文件 docs/adr/D-*.md
- frontmatter 是关系与状态的唯一事实源；正文不重复关系清单
- status 只能通过 `transition` 子命令修改，不得手改
- 看板 `board` 子命令生成，纯静态单文件，直接 open

运行 `python3 scripts/taskdag.py help` 查看完整 schema 契约。
"""

import argparse
import html as html_mod
import json
import math
import os
import re
import sys
from datetime import date
from pathlib import Path

VERSION = "0.2.0"

# ───────────────────────── 常量区（项目级约定） ─────────────────────────

ROOT = Path(__file__).resolve().parent.parent  # scripts/ 的上一级 = 仓库根
TASK_DIR = "docs/tasks"
ADR_DIR = "docs/adr"
DOCS_DIR = "docs"  # source 字段相对此目录解析
# 看板输出路径：相对路径基于仓库根；也可写绝对路径，把看板发布到仓库外（如公网目录）
BOARD_FILE = "docs/tasks/TASK-DAG.html"
BOARD_TITLE = "Task DAG"
# 看板头部的目标/背景一行（当前目标不是任务、不进 DAG，用这行保持可见；空串则不显示）
BOARD_NOTE = ""
# 浏览器标签页图标（data URI，内联 SVG；项目可换成自己的以便在标签栏定位）
# 默认：层叠任务卡·蓝双调（后卡浅蓝、前卡主蓝白描边，透明背景，浅/深标签栏均可辨）
BOARD_ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
              "%3Crect x='13.2' y='2' width='17' height='15' rx='3.4' fill='%238dbdf0'/%3E"
              "%3Crect x='1.8' y='15' width='17' height='15' rx='3.4' fill='%232a78d6'"
              " stroke='%23ffffff' stroke-width='2.2'/%3E%3C/svg%3E")

TASK_ID_RE = re.compile(r"\AT-\d{3}\Z")
ADR_ID_RE = re.compile(r"\AD-\d{3}\Z")
TASK_GLOB = "T-*.md"
ADR_GLOB = "D-*.md"
# 新编号下限（历史编号被归档文档占用时抬高下限，编号永不复用）
NUMBER_FLOOR = {"task": 1, "adr": 1}

TASK_STATUSES = ["planned", "in_progress", "review", "done", "blocked", "cancelled"]
ADR_STATUSES = ["proposed", "accepted", "deprecated", "superseded", "rejected"]
TRANSITIONS = {
    "planned": ["in_progress", "blocked", "cancelled"],
    "in_progress": ["review", "blocked", "cancelled"],
    "review": ["in_progress", "done", "blocked", "cancelled"],
    "done": [],
    "blocked": ["planned", "in_progress", "cancelled"],
    "cancelled": [],
}
TERMINAL_STATUSES = {"done", "cancelled"}

OWNERS = ["agent", "human"]
MODEL_TIERS = ["high", "mid"]
EFFORTS = ["mid", "high", "xhigh", "max"]
PRIORITIES = ["p0", "p1", "p2"]
MANUAL_ACCEPTANCE = ["none", "required"]
HUMAN_CHECKPOINT = ["next"]

TASK_KEYS = {
    "type", "id", "title", "status", "priority", "owner", "model-tier", "effort",
    "manual_acceptance", "human_checkpoint", "depends_on", "related_adrs",
    "source", "area", "phase", "updated",
}
ADR_KEYS = {
    "type", "id", "title", "status", "date", "updated", "area",
    "supersedes", "superseded_by", "related_adrs", "source",
}

REQUIRED_TASK_SECTIONS = ["启动条件", "目标", "交付物", "验收与证据", "非目标"]
OPTIONAL_TASK_SECTIONS = ["执行记录"]
REQUIRED_ADR_SECTIONS = ["背景", "决策"]
DEFAULT_START_CONDITION = "无额外启动条件；仅需满足 `depends_on`。"
EXEC_LOG_HEADING = "执行记录"

DATE_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")
WIKILINK_RE = re.compile(r"\[\[([TD]-\d{3})(?:\|[^\]]*)?\]\]")

# ───────────────────────── frontmatter 解析（严格子集） ─────────────────────────


class DocError(Exception):
    pass


FRONT_RE = re.compile(r"\A---\n(.*?\n)---\n", re.S)
KEY_RE = re.compile(r"\A([a-z][a-z0-9_-]*):(?:[ \t]+(.*))?\Z")
ITEM_RE = re.compile(r"\A[ \t]+-[ \t]+(.*)\Z")


def _unquote(value):
    value = value.strip()
    for quote in ('"', "'"):
        if len(value) >= 2 and value.startswith(quote) and value.endswith(quote):
            return value[1:-1]
    return value


def parse_frontmatter(text):
    """返回 (data, body)。frontmatter 只接受严格子集：
    `key: 标量` / `key: []` / `key:` + 缩进 `- 项` 列表。不接受注释、空行、嵌套映射。"""
    match = FRONT_RE.match(text)
    if not match:
        raise DocError("missing or malformed YAML frontmatter (must open and close with ---)")
    data = {}
    pending_key = None
    for raw in match.group(1).split("\n")[:-1]:
        item = ITEM_RE.match(raw)
        if item:
            if pending_key is None:
                raise DocError(f"list item without a key: {raw!r}")
            data[pending_key].append(_unquote(item.group(1)))
            continue
        key_match = KEY_RE.match(raw)
        if not key_match:
            raise DocError(f"unsupported frontmatter line: {raw!r} "
                           "(allowed: 'key: value', 'key: []', 'key:' + '- item' lines)")
        key, value = key_match.group(1), key_match.group(2)
        if key in data:
            raise DocError(f"duplicate frontmatter key: {key}")
        if value is None or value.strip() == "":
            data[key] = []
            pending_key = key
        elif value.strip() == "[]":
            data[key] = []
            pending_key = None
        else:
            data[key] = _unquote(value)
            pending_key = None
    return data, text[match.end():]


H2_RE = re.compile(r"\A##[ \t]+(.+?)[ \t]*\Z")
H3_RE = re.compile(r"\A###[ \t]+(.+?)[ \t]*\Z")


def split_sections(body):
    """按二级标题切分正文，返回 [(heading, content)]；首个标题前的引言丢给 heading=None。"""
    sections = []
    heading, buf = None, []
    for line in body.split("\n"):
        h2 = H2_RE.match(line)
        if h2:
            sections.append((heading, "\n".join(buf).strip()))
            heading, buf = h2.group(1), []
        else:
            buf.append(line)
    sections.append((heading, "\n".join(buf).strip()))
    return sections


def subsection(content, heading):
    """从章节内容中取 `### heading` 小节内容；不存在返回 None。"""
    lines = content.split("\n")
    start = None
    for i, line in enumerate(lines):
        h3 = H3_RE.match(line)
        if h3 and h3.group(1) == heading:
            start = i + 1
            break
    if start is None:
        return None
    out = []
    for line in lines[start:]:
        if H3_RE.match(line):
            break
        out.append(line)
    return "\n".join(out).strip()


class Doc:
    def __init__(self, path, data=None, body="", error=None):
        self.path = path
        self.data = data or {}
        self.body = body
        self.error = error

    @property
    def id(self):
        return self.data.get("id")

    @property
    def type(self):
        return self.data.get("type")

    @property
    def status(self):
        return self.data.get("status")


def rel(path):
    return str(Path(path).resolve().relative_to(ROOT))


def load_all():
    docs = []
    for directory, glob in ((TASK_DIR, TASK_GLOB), (ADR_DIR, ADR_GLOB)):
        base = ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.glob(glob)):
            text = path.read_text(encoding="utf-8")
            try:
                data, body = parse_frontmatter(text)
                docs.append(Doc(path, data, body))
            except DocError as err:
                docs.append(Doc(path, error=str(err)))
    return docs


def tasks_of(docs):
    return [d for d in docs if d.type == "task"]


def adrs_of(docs):
    return [d for d in docs if d.type == "adr"]


def by_id(docs):
    return {d.id: d for d in docs if d.id}


def as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def deps_done(task, index):
    return all(
        index.get(dep) is not None and index[dep].status == "done"
        for dep in as_list(task.data.get("depends_on"))
    )


def is_runnable(task, index):
    return task.status == "planned" and deps_done(task, index)


# ───────────────────────── validate ─────────────────────────


def validate(docs):
    errors = []
    index = {}
    for doc in docs:
        path = rel(doc.path)
        if doc.error:
            errors.append(f"{path}: {doc.error}")
            continue
        doc_id = doc.id
        if not isinstance(doc_id, str) or not doc_id:
            errors.append(f"{path}: missing id")
        elif doc_id in index:
            errors.append(f"{path}: duplicate id {doc_id}")
        else:
            index[doc_id] = doc

    tasks = tasks_of(docs)
    adrs = adrs_of(docs)

    for doc in docs:
        if doc.error:
            continue
        path, data = rel(doc.path), doc.data
        if data.get("type") not in ("task", "adr"):
            errors.append(f"{path}: type must be task or adr")
            continue
        for field in ("title", "status", "updated"):
            if not data.get(field):
                errors.append(f"{path}: missing {field}")
        if data.get("updated") and not DATE_RE.match(str(data["updated"])):
            errors.append(f"{path}: updated must be YYYY-MM-DD")
        if "tags" in data:
            errors.append(f"{path}: tags is not allowed")

    for doc in tasks:
        if doc.error:
            continue
        path, data = rel(doc.path), doc.data
        doc_id = data.get("id", "")
        if not TASK_ID_RE.match(doc_id or ""):
            errors.append(f"{path}: task id must match T-<3 digits>")
        elif doc.path.name != f"{doc_id}.md":
            errors.append(f"{path}: filename must be {doc_id}.md")
        unknown = set(data) - TASK_KEYS
        if unknown:
            errors.append(f"{path}: unknown task keys: {', '.join(sorted(unknown))}")
        if data.get("status") not in TASK_STATUSES:
            errors.append(f"{path}: invalid task status {data.get('status')!r}")
        if data.get("priority") not in PRIORITIES:
            errors.append(f"{path}: task requires priority ({'/'.join(PRIORITIES)})")
        owner = data.get("owner")
        if owner not in OWNERS:
            errors.append(f"{path}: owner must be one of {'/'.join(OWNERS)}")
        tier, effort = data.get("model-tier"), data.get("effort")
        if owner == "agent":
            if tier not in MODEL_TIERS:
                errors.append(f"{path}: agent task requires model-tier ({'/'.join(MODEL_TIERS)})")
            if effort not in EFFORTS:
                errors.append(f"{path}: agent task requires effort ({'/'.join(EFFORTS)})")
        elif owner == "human":
            if tier is not None or effort is not None:
                errors.append(f"{path}: human task must not declare model-tier/effort")
        if data.get("manual_acceptance") not in MANUAL_ACCEPTANCE:
            errors.append(f"{path}: manual_acceptance must be none or required")
        if "human_checkpoint" in data and data["human_checkpoint"] not in HUMAN_CHECKPOINT:
            errors.append(f"{path}: human_checkpoint must be next when present")
        if not isinstance(data.get("depends_on"), list):
            errors.append(f"{path}: depends_on must be a list (use [] when empty)")
        else:
            for dep in data["depends_on"]:
                if not TASK_ID_RE.match(dep):
                    errors.append(f"{path}: dependency must be a plain task id: {dep!r}")
                elif dep == doc_id:
                    errors.append(f"{path}: task cannot depend on itself")
                elif index.get(dep) is None or index[dep].type != "task":
                    errors.append(f"{path}: unknown dependency {dep}")
        if "related_adrs" in data:
            if not isinstance(data["related_adrs"], list):
                errors.append(f"{path}: related_adrs must be a list")
            else:
                for adr in data["related_adrs"]:
                    if not ADR_ID_RE.match(adr):
                        errors.append(f"{path}: related ADR must be a plain ADR id: {adr!r}")
                    elif index.get(adr) is None or index[adr].type != "adr":
                        errors.append(f"{path}: unknown related ADR {adr}")
        source = data.get("source")
        if source is not None:
            if isinstance(source, list) or re.search(r"[\[\]|]", source):
                errors.append(f"{path}: source must be a plain doc reference without wikilink markup")
            else:
                name, _, heading = source.partition("#")
                source_path = ROOT / DOCS_DIR / f"{name}.md"
                if not source_path.is_file():
                    errors.append(f"{path}: source file does not exist: {name}")
                elif heading:
                    text = source_path.read_text(encoding="utf-8")
                    pattern = re.compile(r"^#{1,6}[ \t]+" + re.escape(heading) + r"[ \t]*$", re.M)
                    if not pattern.search(text):
                        errors.append(f"{path}: source heading does not exist: {heading}")

        sections = split_sections(doc.body)
        counts = {}
        for heading, content in sections:
            if heading:
                counts.setdefault(heading, []).append(content)
        for heading in REQUIRED_TASK_SECTIONS:
            found = counts.get(heading, [])
            if len(found) != 1 or not found[0]:
                errors.append(f"{path}: task must contain exactly one non-empty `## {heading}`")
        for heading in counts:
            if heading not in REQUIRED_TASK_SECTIONS + OPTIONAL_TASK_SECTIONS:
                errors.append(f"{path}: unexpected section `## {heading}`")
        start = counts.get("启动条件", [""])[0]
        if data.get("status") == "blocked" and start == DEFAULT_START_CONDITION:
            errors.append(f"{path}: blocked task must describe its concrete external start conditions")
        acceptance = counts.get("验收与证据", [""])[0]
        if acceptance:
            manual = subsection(acceptance, "人工验收")
            heads = len(re.findall(r"^###[ \t]+人工验收[ \t]*$", acceptance, re.M))
            if heads != 1 or manual is None:
                errors.append(f"{path}: 验收与证据 must contain exactly one `### 人工验收` subsection")
            elif data.get("manual_acceptance") == "none":
                if manual != "无。":
                    errors.append(f"{path}: manual_acceptance none requires 人工验收 to contain only `无。`")
            elif data.get("manual_acceptance") == "required":
                actions = re.findall(r"^-[ \t]+最小动作：(.+)$", manual, re.M)
                standards = re.findall(r"^-[ \t]+通过标准：(.+)$", manual, re.M)
                if len(actions) != 1 or len(standards) != 1 \
                        or not actions[0].strip() or not standards[0].strip():
                    errors.append(f"{path}: manual_acceptance required needs exactly one "
                                  "`- 最小动作：...` and one `- 通过标准：...`")

    checkpoints = [d for d in tasks if not d.error and d.data.get("human_checkpoint") == "next"]
    if len(checkpoints) > 1:
        ids = ", ".join(sorted(d.id for d in checkpoints))
        errors.append(f"multiple tasks declare human_checkpoint next: {ids}")
    for doc in checkpoints:
        if doc.data.get("manual_acceptance") != "required":
            errors.append(f"{rel(doc.path)}: human_checkpoint next requires manual_acceptance required")
        if doc.status in TERMINAL_STATUSES:
            errors.append(f"{rel(doc.path)}: terminal task cannot remain human_checkpoint next")

    for doc in adrs:
        if doc.error:
            continue
        path, data = rel(doc.path), doc.data
        doc_id = data.get("id", "")
        if not ADR_ID_RE.match(doc_id or ""):
            errors.append(f"{path}: ADR id must match D-<3 digits>")
        elif doc.path.name != f"{doc_id}.md":
            errors.append(f"{path}: filename must be {doc_id}.md")
        unknown = set(data) - ADR_KEYS
        if unknown:
            errors.append(f"{path}: unknown ADR keys: {', '.join(sorted(unknown))}")
        if data.get("status") not in ADR_STATUSES:
            errors.append(f"{path}: invalid ADR status {data.get('status')!r}")
        if not data.get("date") or not DATE_RE.match(str(data.get("date", ""))):
            errors.append(f"{path}: ADR requires date (YYYY-MM-DD, 决策日)")
        if "depends_on" in data:
            errors.append(f"{path}: ADR must not define task depends_on")
        for relation in ("supersedes", "superseded_by", "related_adrs"):
            for target in as_list(data.get(relation)):
                if not ADR_ID_RE.match(target):
                    errors.append(f"{path}: {relation} must contain plain ADR ids: {target!r}")
                elif target == doc_id:
                    errors.append(f"{path}: ADR cannot {relation} itself")
                elif index.get(target) is None or index[target].type != "adr":
                    errors.append(f"{path}: unknown {relation} ADR {target}")
        for old in as_list(data.get("supersedes")):
            if index.get(old) is not None and doc_id not in as_list(index[old].data.get("superseded_by")):
                errors.append(f"{path}: {old} must declare superseded_by {doc_id}")
        for new in as_list(data.get("superseded_by")):
            if index.get(new) is not None and doc_id not in as_list(index[new].data.get("supersedes")):
                errors.append(f"{path}: {new} must declare supersedes {doc_id}")
        if data.get("status") == "superseded" and not as_list(data.get("superseded_by")):
            errors.append(f"{path}: superseded ADR must declare superseded_by")
        if as_list(data.get("superseded_by")) and data.get("status") != "superseded":
            errors.append(f"{path}: ADR with superseded_by must have status superseded")
        sections = split_sections(doc.body)
        counts = {}
        for heading, content in sections:
            if heading:
                counts.setdefault(heading, []).append(content)
        for heading in REQUIRED_ADR_SECTIONS:
            found = counts.get(heading, [])
            if len(found) != 1 or not found[0]:
                errors.append(f"{path}: ADR must contain exactly one non-empty `## {heading}`")

    # wikilink 目标存在性（只扫 task/adr 正文）
    known = set(index)
    for doc in docs:
        if doc.error:
            continue
        for target in WIKILINK_RE.findall(doc.body):
            if target not in known:
                errors.append(f"{rel(doc.path)}: unknown wikilink target {target}")

    # 依赖环检测
    graph = {d.id: [dep for dep in as_list(d.data.get("depends_on")) if dep in known]
             for d in tasks if not d.error and d.id}
    color = {}
    def visit(node, trail):
        if color.get(node) == "black":
            return
        if color.get(node) == "gray":
            errors.append("task dependency cycle: " + " -> ".join(trail + [node]))
            return
        color[node] = "gray"
        for dep in graph.get(node, []):
            visit(dep, trail + [node])
        color[node] = "black"
    for node in graph:
        visit(node, [])

    return errors


# ───────────────────────── query ─────────────────────────


def query(docs, filters, as_json=False):
    index = by_id(docs)
    rows = []
    for doc in docs:
        if doc.error:
            continue
        computed = dict(doc.data)
        if doc.type == "task":
            computed["runnable"] = "true" if is_runnable(doc, index) else "false"
        matched = True
        for key, value in filters.items():
            actual = computed.get(key)
            if isinstance(actual, list):
                matched = value in actual
            else:
                matched = str(actual) == value if actual is not None else False
            if not matched:
                break
        if matched:
            rows.append((doc, computed))
    rows.sort(key=lambda pair: (pair[0].type, pair[0].id or ""))
    if as_json:
        print(json.dumps([c for _, c in rows], ensure_ascii=False, indent=2))
        return
    for doc, computed in rows:
        if doc.type == "task":
            owner = computed.get("owner", "?")
            gear = f"{computed.get('model-tier')}/{computed.get('effort')}" if owner == "agent" else "-"
            flags = []
            if computed["runnable"] == "true":
                flags.append("runnable")
            if computed.get("human_checkpoint") == "next":
                flags.append("checkpoint")
            if computed.get("manual_acceptance") == "required":
                flags.append("manual")
            flag_str = ",".join(flags)
            print(f"{doc.id}  {computed.get('status', ''):<11} {computed.get('priority', '?'):<4} "
                  f"{owner:<6} {gear:<11} {flag_str:<26} {computed.get('title', '')}")
        else:
            print(f"{doc.id}  {computed.get('status', ''):<11} {computed.get('title', '')}")
    if not rows:
        print("(no match)")


# ───────────────────────── transition ─────────────────────────


def today():
    return os.environ.get("TASKDAG_TODAY") or date.today().isoformat()


def transition(doc_id, new_status, reason):
    docs = load_all()
    index = by_id(docs)
    doc = index.get(doc_id)
    if doc is None or doc.type != "task":
        sys.exit(f"error: unknown task {doc_id}")
    old_status = doc.status
    if new_status not in TASK_STATUSES:
        sys.exit(f"error: invalid status {new_status!r} (allowed: {', '.join(TASK_STATUSES)})")
    if new_status not in TRANSITIONS.get(old_status, []):
        allowed = ", ".join(TRANSITIONS.get(old_status, [])) or "(terminal)"
        sys.exit(f"error: illegal transition {old_status} -> {new_status}; allowed from {old_status}: {allowed}")

    original = doc.path.read_text(encoding="utf-8")
    match = FRONT_RE.match(original)
    front_lines = match.group(1).split("\n")[:-1]
    out_lines = []
    for line in front_lines:
        if line.startswith("status:"):
            out_lines.append(f"status: {new_status}")
        elif line.startswith("updated:"):
            out_lines.append(f"updated: {today()}")
        elif line.startswith("human_checkpoint:") and new_status in TERMINAL_STATUSES:
            continue  # 终态自动摘除检查点指针
        else:
            out_lines.append(line)
    body = original[match.end():]

    log_line = f"- {today()} `{old_status} → {new_status}`" + (f"：{reason}" if reason else "")
    heading = f"## {EXEC_LOG_HEADING}"
    lines = body.split("\n")
    idx = next((i for i, line in enumerate(lines) if line.strip() == heading), None)
    if idx is None:
        body = body.rstrip("\n") + f"\n\n{heading}\n\n{log_line}\n"
    else:
        j = idx + 1
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        lines[idx + 1:j] = ["", log_line, ""] if j < len(lines) else ["", log_line]
        body = "\n".join(lines)

    doc.path.write_text("---\n" + "\n".join(out_lines) + "\n---\n" + body, encoding="utf-8")
    errors = validate(load_all())
    if errors:
        doc.path.write_text(original, encoding="utf-8")
        print("transition reverted; repository would become invalid:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        sys.exit(1)
    print(f"{doc_id}: {old_status} -> {new_status}")
    if new_status in TERMINAL_STATUSES and doc.data.get("human_checkpoint") == "next":
        print("note: human_checkpoint next removed; pick and mark the next checkpoint task")


# ───────────────────────── new ─────────────────────────

TASK_TEMPLATE = """---
type: task
id: {id}
title: {title}
status: planned
priority: {priority}
owner: {owner}
{gear}manual_acceptance: {manual}
depends_on:{deps}
{adrs}updated: {today}
---

## 启动条件

{start_condition}

## 目标

（一句话说清做完后世界有什么不同。）

## 交付物

- （可验收的产出清单。）

## 验收与证据

（客观证据怎么拿：命令、数据、截图。）

### 人工验收

{manual_body}

## 非目标

（明确不做什么，防止范围蔓延。）
"""

ADR_TEMPLATE = """---
type: adr
id: {id}
title: {title}
status: proposed
date: {today}
updated: {today}
---

## 背景

（为什么需要这个决定；不决定会怎样。）

## 决策

（决定本身，以及被否掉的替代方案。）
"""


def next_id(kind):
    docs = load_all()
    pool = tasks_of(docs) if kind == "task" else adrs_of(docs)
    prefix = "T-" if kind == "task" else "D-"
    highest = NUMBER_FLOOR.get(kind, 1) - 1
    for doc in pool:
        if doc.id and doc.id.startswith(prefix):
            try:
                highest = max(highest, int(doc.id[len(prefix):]))
            except ValueError:
                pass
    return f"{prefix}{highest + 1:03d}"


def new_doc(kind, title, owner, tier, effort, manual, deps, adrs, priority):
    doc_id = next_id(kind)
    if kind == "task":
        if owner == "agent":
            if tier not in MODEL_TIERS or effort not in EFFORTS:
                sys.exit("error: agent task requires --model-tier and --effort")
            gear = f"model-tier: {tier}\neffort: {effort}\n"
        else:
            gear = ""
        deps_value = " []" if not deps else "\n" + "\n".join(f"  - {d}" for d in deps)
        adr_value = "" if not adrs else "related_adrs:\n" + "\n".join(f"  - {a}" for a in adrs) + "\n"
        manual_body = "无。" if manual == "none" else "- 最小动作：（一步动作）\n- 通过标准：（一条标准）"
        content = TASK_TEMPLATE.format(
            id=doc_id, title=title, owner=owner, gear=gear, manual=manual,
            deps=deps_value, adrs=adr_value, today=today(), priority=priority,
            start_condition=DEFAULT_START_CONDITION, manual_body=manual_body)
        path = ROOT / TASK_DIR / f"{doc_id}.md"
    else:
        content = ADR_TEMPLATE.format(id=doc_id, title=title, today=today())
        path = ROOT / ADR_DIR / f"{doc_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        sys.exit(f"error: {rel(path)} already exists")
    path.write_text(content, encoding="utf-8")
    errors = validate(load_all())
    if errors:
        path.unlink()
        print("document not created; it would make the repository invalid:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        sys.exit(1)
    print(rel(path))


# ───────────────────────── markdown 渲染（构建期，供看板 detail） ─────────────────────────


INLINE_RULES = [
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])"), r"<em>\1</em>"),
    (re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)"), r'<a href="\2" rel="noopener">\1</a>'),
]


def render_inline(text):
    out = html_mod.escape(text, quote=False)
    for pattern, repl in INLINE_RULES:
        out = pattern.sub(repl, out)
    out = re.sub(r"\[\[([TD]-\d{3})\|([^\]]+)\]\]",
                 r'<a href="#" class="doclink" data-doc="\1">\2</a>', out)
    out = re.sub(r"\[\[([TD]-\d{3})\]\]",
                 r'<a href="#" class="doclink" data-doc="\1">\1</a>', out)
    return out


def render_markdown(body):
    lines = body.split("\n")
    out, i = [], 0
    list_stack = []  # 元素为 "ul"/"ol"

    def close_lists(depth=0):
        while len(list_stack) > depth:
            out.append(f"</{list_stack.pop()}>")

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            close_lists()
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            out.append("<pre><code>" + html_mod.escape("\n".join(block)) + "</code></pre>")
            i += 1
            continue
        heading = re.match(r"\A(#{2,4})[ \t]+(.+?)[ \t]*\Z", line)
        if heading:
            close_lists()
            level = len(heading.group(1)) + 2  # ## -> h4, ### -> h5
            out.append(f"<h{level}>{render_inline(heading.group(2))}</h{level}>")
            i += 1
            continue
        item = re.match(r"\A([ \t]*)(-|\d+\.)[ \t]+(.+)\Z", line)
        if item:
            depth = 1 if len(item.group(1)) >= 2 else 0
            kind = "ol" if item.group(2) != "-" else "ul"
            while len(list_stack) > depth + 1:
                out.append(f"</{list_stack.pop()}>")
            if len(list_stack) == depth + 1 and list_stack[-1] != kind:
                out.append(f"</{list_stack.pop()}>")
            while len(list_stack) < depth + 1:
                list_stack.append(kind)
                out.append(f"<{kind}>")
            out.append(f"<li>{render_inline(item.group(3))}</li>")
            i += 1
            continue
        if line.startswith(">"):
            close_lists()
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip("> "))
                i += 1
            out.append("<blockquote><p>" + render_inline(" ".join(quote)) + "</p></blockquote>")
            continue
        if line.strip() == "":
            close_lists()
            i += 1
            continue
        close_lists()
        paragraph = [line]
        while i + 1 < len(lines) and lines[i + 1].strip() != "" \
                and not re.match(r"\A([ \t]*)(-|\d+\.|#|>|```)", lines[i + 1]):
            i += 1
            paragraph.append(lines[i])
        out.append("<p>" + render_inline(" ".join(paragraph)) + "</p>")
        i += 1
    close_lists()
    return "\n".join(out)


# ───────────────────────── board ─────────────────────────


def layout(task_rows):
    """最长路径分层：layer = 1 + max(依赖 layer)。返回 {id: (layer, row)}。"""
    ids = {row["id"] for row in task_rows}
    deps = {row["id"]: [d for d in row["deps"] if d in ids] for row in task_rows}
    layer_of = {}

    def layer(node, seen):
        if node in layer_of:
            return layer_of[node]
        if node in seen:  # 有环时兜底（validate 会报错，这里保证不崩）
            return 0
        seen = seen | {node}
        value = 0 if not deps[node] else 1 + max(layer(d, seen) for d in deps[node])
        layer_of[node] = value
        return value

    for node in deps:
        layer(node, frozenset())
    columns = {}
    for row in task_rows:
        columns.setdefault(layer_of[row["id"]], []).append(row)
    positions = {}
    for col, rows in columns.items():
        rows.sort(key=lambda r: r["id"])
        for idx, row in enumerate(rows):
            positions[row["id"]] = (col, idx)
    return positions


def board():
    docs = load_all()
    errors = validate(docs)
    if errors:
        print("board not generated; fix validation errors first:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        sys.exit(1)
    index = by_id(docs)
    task_rows, adr_rows = [], []
    for doc in tasks_of(docs):
        task_rows.append({
            "id": doc.id, "title": doc.data.get("title", ""), "status": doc.status,
            "priority": doc.data.get("priority"),
            "owner": doc.data.get("owner"), "tier": doc.data.get("model-tier"),
            "effort": doc.data.get("effort"),
            "manual": doc.data.get("manual_acceptance"),
            "checkpoint": doc.data.get("human_checkpoint") == "next",
            "deps": as_list(doc.data.get("depends_on")),
            "adrs": as_list(doc.data.get("related_adrs")),
            "source": doc.data.get("source"), "updated": doc.data.get("updated"),
            "runnable": is_runnable(doc, index),
            "html": render_markdown(doc.body),
        })
    for doc in adrs_of(docs):
        adr_rows.append({
            "id": doc.id, "title": doc.data.get("title", ""), "status": doc.status,
            "date": doc.data.get("date"), "updated": doc.data.get("updated"),
            "supersedes": as_list(doc.data.get("supersedes")),
            "superseded_by": as_list(doc.data.get("superseded_by")),
            "related": as_list(doc.data.get("related_adrs")),
            "html": render_markdown(doc.body),
        })

    node_w, gap_x, gap_y, margin = 232, 72, 22, 24
    # 标题与徽标行都完整显示：按 CJK/拉丁宽度估算各自行数，节点高度随之变化
    per_line = (node_w - 22) / 13.0

    def text_w(s):
        return sum(10 if ord(ch) > 0x2E7F else 5.5 for ch in s)

    for row in task_rows:
        badges = [row["priority"] or "?"]
        if row["checkpoint"]:
            badges.append("检查点")
        badges.append("人" if row["owner"] == "human" else f"{row['tier']}/{row['effort']}")
        if row["manual"] == "required":
            badges.append("人工验收")
        avail = node_w - 28
        x, nid_lines = text_w(row["id"]), 1
        for badge in badges:
            bw = text_w(badge) + 12  # 徽标内边距与边框
            if x + 6 + bw > avail:
                nid_lines += 1
                x = bw
            else:
                x += 6 + bw
        title_lines = max(1, math.ceil(
            sum(1.0 if ord(ch) > 0x2E7F else 0.55 for ch in row["title"]) / per_line))
        row["h"] = 14 + nid_lines * 18 + title_lines * 17 + 8
    positions = layout(task_rows)
    columns = {}
    for row in task_rows:
        columns.setdefault(positions[row["id"]][0], []).append(row)
    prio_rank = {p: i for i, p in enumerate(PRIORITIES)}
    canvas_h = margin * 2
    for col, rows in sorted(columns.items()):
        rows.sort(key=lambda r: (prio_rank.get(r["priority"], 9), r["id"]))
        y = margin
        for row in rows:
            row["x"] = margin + col * (node_w + gap_x)
            row["y"] = y
            y += row["h"] + gap_y
        canvas_h = max(canvas_h, y - gap_y + margin)
    max_col = max(columns, default=0)
    canvas_w = margin * 2 + (max_col + 1) * node_w + max_col * gap_x

    payload = json.dumps({"tasks": task_rows, "adrs": adr_rows,
                          "generated": today(), "nodeW": node_w},
                         ensure_ascii=False).replace("</", "<\\/")
    html_out = BOARD_TEMPLATE.replace("__TITLE__", html_mod.escape(BOARD_TITLE)) \
                             .replace("__ICON__", BOARD_ICON) \
                             .replace("__NOTE__", html_mod.escape(BOARD_NOTE)) \
                             .replace("__CANVAS_W__", str(canvas_w)) \
                             .replace("__CANVAS_H__", str(canvas_h)) \
                             .replace("__DATA__", payload)
    out_path = Path(BOARD_FILE)
    if not out_path.is_absolute():
        out_path = ROOT / BOARD_FILE
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_out, encoding="utf-8")
    try:
        label = rel(out_path)
    except ValueError:
        label = str(out_path)
    print(f"{label}  ({len(task_rows)} tasks, {len(adr_rows)} ADRs)")


BOARD_TEMPLATE = r"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="__ICON__">
<title>__TITLE__</title>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e;
  --muted: #898781; --hairline: #e1e0d9; --baseline: #c3c2b7;
  --border: rgba(11,11,11,0.10);
  --accent: #2a78d6; --st-in-progress: #1baf7a; --st-review: #4a3aa7;
  --st-done: #0ca30c; --st-blocked: #ec835a; --st-planned: #898781;
  --st-cancelled: #c3c2b7;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7;
    --muted: #898781; --hairline: #2c2c2a; --baseline: #383835;
    --border: rgba(255,255,255,0.10);
    --accent: #3987e5; --st-in-progress: #199e70; --st-review: #9085e9;
    --st-done: #0ca30c; --st-blocked: #ec835a; --st-planned: #898781;
    --st-cancelled: #52514e;
  }
}
* { box-sizing: border-box; margin: 0; }
body {
  background: var(--page); color: var(--ink);
  font: 14px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
  padding: 20px;
}
h1 { font-size: 18px; font-weight: 650; }
.sub { color: var(--muted); font-size: 12px; margin-top: 2px; }
#goalnote { color: var(--ink-2); font-weight: 600; }
#goalnote:empty { display: none; }
header { display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: baseline; margin-bottom: 14px; }
.counts { display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; }
.count { background: var(--surface); border: 1px solid var(--border); border-radius: 999px;
  padding: 2px 10px; color: var(--ink-2); }
.count b { color: var(--ink); font-weight: 650; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; }
.tabs { display: flex; gap: 2px; margin-bottom: 12px; border-bottom: 1px solid var(--hairline); }
.tab { border: 0; background: none; color: var(--ink-2); font: inherit; padding: 6px 14px;
  cursor: pointer; border-bottom: 2px solid transparent; }
.tab[aria-selected="true"] { color: var(--ink); font-weight: 650; border-bottom-color: var(--accent); }
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
.toolbar input[type="search"] {
  background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  color: var(--ink); font: inherit; padding: 5px 10px; width: 220px;
}
.chip { border: 1px solid var(--border); background: var(--surface); border-radius: 999px;
  color: var(--ink-2); font-size: 12px; padding: 3px 10px; cursor: pointer; }
.chip[aria-pressed="true"] { color: var(--ink); border-color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent); }
.layout { display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: 14px; align-items: start; }
@media (max-width: 980px) { .layout { grid-template-columns: 1fr; } }
.panel { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; }
.graph-wrap { overflow: auto; max-height: 74vh; }
.canvas { position: relative; }
.canvas svg { position: absolute; inset: 0; pointer-events: none; }
.edge { stroke: var(--baseline); stroke-width: 1.5; fill: none; }
.edge.hi { stroke: var(--accent); stroke-width: 2; }
.edge.dim, .node.dim { opacity: 0.18; }
.node { position: absolute; background: var(--surface); border: 1px solid var(--border);
  border-left: 4px solid var(--st-planned); border-radius: 3px; padding: 7px 10px;
  cursor: pointer; overflow: hidden; }
.node:hover { border-color: var(--accent); }
.node.sel { outline: 2px solid var(--accent); outline-offset: 1px; }
.node .nid { font-size: 11px; color: var(--ink-2); display: flex; gap: 4px 6px;
  align-items: center; flex-wrap: wrap; }
.node .tid { flex-shrink: 0; white-space: nowrap; }
.node .ntitle { font-size: 12.5px; font-weight: 600; line-height: 1.35;
  overflow-wrap: break-word; }
.node.st-in_progress { border-left-color: var(--st-in-progress); }
.node.st-review { border-left-color: var(--st-review); }
.node.st-done { border-left-color: var(--st-done); opacity: 0.55; }
.node.st-blocked { border-left-color: var(--st-blocked); border-style: dashed; border-left-style: solid; }
.node.st-cancelled { border-left-color: var(--st-cancelled); opacity: 0.45; }
.node.st-cancelled .ntitle { text-decoration: line-through; }
.node.runnable { box-shadow: inset 0 0 0 1px var(--accent); border-color: var(--accent); }
.badge { font-size: 10px; border-radius: 3px; padding: 0 5px; border: 1px solid var(--border);
  color: var(--ink-2); white-space: nowrap; }
.badge.ckpt { color: var(--accent); border-color: var(--accent); font-weight: 650; }
.badge.prio { font-weight: 650; }
.detail { padding: 14px 16px; max-height: 74vh; overflow: auto; font-size: 13px; }
.detail .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 10px; }
.detail h2 { font-size: 15px; margin-top: 2px; }
.detail h4 { font-size: 12.5px; margin: 14px 0 4px; color: var(--ink-2);
  text-transform: none; border-bottom: 1px solid var(--hairline); padding-bottom: 3px; }
.detail h5 { font-size: 12px; margin: 10px 0 3px; color: var(--ink-2); }
.detail p, .detail li { color: var(--ink); }
.detail ul, .detail ol { padding-left: 20px; margin: 4px 0; }
.detail code { background: var(--page); border: 1px solid var(--hairline); border-radius: 4px;
  padding: 0 4px; font-size: 12px; }
.detail pre { background: var(--page); border: 1px solid var(--hairline); border-radius: 8px;
  padding: 10px; overflow-x: auto; margin: 6px 0; }
.detail pre code { border: 0; background: none; padding: 0; }
.detail blockquote { border-left: 3px solid var(--hairline); margin: 6px 0; padding: 2px 10px;
  color: var(--ink-2); }
.detail .meta { color: var(--muted); font-size: 12px; }
.detail a { color: var(--accent); text-decoration: none; }
.detail a:hover { text-decoration: underline; }
.empty { color: var(--muted); padding: 30px; text-align: center; }
.ready { padding: 10px 14px; border-top: 1px solid var(--hairline); font-size: 12.5px; }
.ready b { font-weight: 650; }
.ready a { color: var(--accent); text-decoration: none; margin-right: 10px; cursor: pointer; }
.adr-list { list-style: none; padding: 6px; }
.adr-list li { display: flex; gap: 10px; align-items: baseline; padding: 7px 10px;
  border-radius: 8px; cursor: pointer; }
.adr-list li:hover, .adr-list li.sel { background: var(--page); }
.adr-list .aid { color: var(--ink-2); font-size: 12px; min-width: 46px; }
.adr-list .atitle { font-weight: 600; font-size: 13px; flex: 1; }
.pill { font-size: 10.5px; border-radius: 999px; padding: 1px 8px; border: 1px solid var(--border);
  color: var(--ink-2); }
.pill .dot { width: 7px; height: 7px; }
footer { color: var(--muted); font-size: 11.5px; margin-top: 12px; }
</style>
</head>
<body>
<header>
  <div>
    <h1>__TITLE__</h1>
    <div class="sub" id="goalnote">__NOTE__</div>
    <div class="sub" id="subline"></div>
  </div>
  <div class="counts" id="counts"></div>
</header>
<div class="tabs" role="tablist">
  <button class="tab" id="tab-tasks" role="tab" aria-selected="true">任务</button>
  <button class="tab" id="tab-adrs" role="tab" aria-selected="false">决策（ADR）</button>
</div>
<div id="view-tasks">
  <div class="toolbar" id="toolbar">
    <input type="search" id="search" placeholder="搜索编号或标题，回车直达…" aria-label="搜索任务">
  </div>
  <div class="layout">
    <div>
      <div class="panel graph-wrap">
        <div class="canvas" id="canvas" style="width:__CANVAS_W__px;height:__CANVAS_H__px">
          <svg id="edges" width="__CANVAS_W__" height="__CANVAS_H__"></svg>
        </div>
      </div>
      <div class="panel ready" id="ready" style="margin-top:10px"></div>
    </div>
    <aside class="panel detail" id="detail"><div class="empty">点击任意节点查看详情</div></aside>
  </div>
</div>
<div id="view-adrs" hidden>
  <div class="layout">
    <div class="panel"><ul class="adr-list" id="adr-list"></ul></div>
    <aside class="panel detail" id="adr-detail"><div class="empty">点击任意决策查看详情</div></aside>
  </div>
</div>
<footer id="foot"></footer>
<script type="application/json" id="data">__DATA__</script>
<script>
(() => {
  const data = JSON.parse(document.getElementById('data').textContent);
  const esc = s => String(s ?? '').replace(/[&<>"]/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const tasks = data.tasks, adrs = data.adrs;
  const byId = new Map(tasks.map(t => [t.id, t]));
  const adrById = new Map(adrs.map(a => [a.id, a]));
  const statusLabel = { planned: '待开始', in_progress: '进行中', review: '待验收',
    done: '已完成', blocked: '阻塞', cancelled: '已取消' };
  const adrStatusLabel = { proposed: '提议', accepted: '生效', deprecated: '不建议',
    superseded: '已取代', rejected: '否决' };
  const ownerLabel = { agent: 'Agent', human: '人' };

  // ── 计数与副标题 ──
  const counts = {};
  tasks.forEach(t => { counts[t.status] = (counts[t.status] || 0) + 1; });
  const runnableTasks = tasks.filter(t => t.runnable);
  document.getElementById('counts').innerHTML =
    Object.keys(statusLabel).filter(s => counts[s]).map(s =>
      `<span class="count"><span class="dot" style="background:var(--st-${s.replace('_','-')})"></span>` +
      `${statusLabel[s]} <b>${counts[s]}</b></span>`).join('') +
    `<span class="count">可开跑 <b>${runnableTasks.length}</b></span>`;
  const checkpoint = tasks.find(t => t.checkpoint);
  document.getElementById('subline').textContent =
    `${tasks.length} 个任务 · ${adrs.length} 项决策` +
    (checkpoint ? ` · 下一检查点：${checkpoint.id} ${checkpoint.title}` : '');
  document.getElementById('foot').textContent =
    `生成于 ${data.generated} · 数据来自 docs/tasks 与 docs/adr 的 frontmatter · ` +
    `修改状态用 python3 scripts/taskdag.py transition，改完重跑 board`;

  // ── 节点与边 ──
  const canvas = document.getElementById('canvas');
  const svg = document.getElementById('edges');
  const nodeEls = new Map(), edgeEls = [];
  tasks.forEach(t => {
    const el = document.createElement('div');
    el.className = `node st-${t.status}` + (t.runnable ? ' runnable' : '');
    el.style.left = t.x + 'px'; el.style.top = t.y + 'px';
    el.style.width = data.nodeW + 'px'; el.style.height = t.h + 'px';
    const badges = [`<span class="badge prio">${t.priority}</span>`];
    if (t.checkpoint) badges.push('<span class="badge ckpt">检查点</span>');
    if (t.owner === 'human') badges.push('<span class="badge">人</span>');
    else badges.push(`<span class="badge">${t.tier}/${t.effort}</span>`);
    if (t.manual === 'required') badges.push('<span class="badge">人工验收</span>');
    el.innerHTML = `<div class="nid"><span class="tid">${t.id}</span>${badges.join('')}</div>` +
      `<div class="ntitle" title="${esc(t.title)}">${esc(t.title)}</div>`;
    el.addEventListener('click', () => selectTask(t.id));
    el.addEventListener('mouseenter', () => hover(t.id, true));
    el.addEventListener('mouseleave', () => hover(t.id, false));
    canvas.appendChild(el);
    nodeEls.set(t.id, el);
  });
  const ns = 'http://www.w3.org/2000/svg';
  const defs = document.createElementNS(ns, 'defs');
  defs.innerHTML = '<marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" ' +
    'markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8 z" fill="var(--baseline)"/></marker>';
  svg.appendChild(defs);
  tasks.forEach(t => t.deps.forEach(dep => {
    const d = byId.get(dep);
    if (!d) return;
    const x1 = d.x + data.nodeW, y1 = d.y + d.h / 2;
    const x2 = t.x, y2 = t.y + t.h / 2;
    const mid = (x1 + x2) / 2;
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2 - 3} ${y2}`);
    path.setAttribute('class', 'edge');
    path.setAttribute('marker-end', 'url(#arrow)');
    path.dataset.from = dep; path.dataset.to = t.id;
    svg.appendChild(path);
    edgeEls.push(path);
  }));
  function hover(id, on) {
    edgeEls.forEach(e => e.classList.toggle('hi',
      on && (e.dataset.from === id || e.dataset.to === id)));
  }

  // ── 筛选 ──
  const toolbar = document.getElementById('toolbar');
  const filters = { status: new Set(), flag: new Set(), prio: new Set() };
  const chipDefs = ['p0', 'p1', 'p2'].map(p => ({ group: 'prio', value: p, label: p }))
    .concat(Object.keys(statusLabel).map(s => ({ group: 'status', value: s, label: statusLabel[s] })))
    .concat([{ group: 'flag', value: 'runnable', label: '可开跑' },
             { group: 'flag', value: 'human', label: '人的任务' }]);
  chipDefs.forEach(def => {
    const b = document.createElement('button');
    b.className = 'chip'; b.textContent = def.label; b.setAttribute('aria-pressed', 'false');
    b.addEventListener('click', () => {
      const set = filters[def.group];
      set.has(def.value) ? set.delete(def.value) : set.add(def.value);
      b.setAttribute('aria-pressed', String(set.has(def.value)));
      applyFilters();
    });
    toolbar.appendChild(b);
  });
  const search = document.getElementById('search');
  search.addEventListener('input', applyFilters);
  // 回车：把输入解析成编号直接定位（12 / t12 / T-012 → T-012；d3 → D-003），
  // 不是编号就打开第一个标题匹配的任务
  function resolveId(q) {
    const m = q.trim().match(/^([td])?[-\s]*0*(\d+)$/i);
    if (m) {
      const n = m[2].padStart(3, '0');
      const cands = m[1] ? [m[1].toUpperCase() + '-' + n] : ['T-' + n, 'D-' + n];
      return cands.find(id => byId.has(id) || adrById.has(id)) || null;
    }
    const ql = q.trim().toLowerCase();
    if (!ql) return null;
    const hit = tasks.find(t => visible(t)) ||
      adrs.find(a => a.id.toLowerCase().includes(ql) || a.title.toLowerCase().includes(ql));
    return hit ? hit.id : null;
  }
  search.addEventListener('keydown', ev => {
    if (ev.key !== 'Enter') return;
    ev.preventDefault();
    const id = resolveId(search.value);
    if (!id) return;
    if (byId.has(id)) { showTab('tasks'); selectTask(id, true); }
    else { showTab('adrs'); selectAdr(id); }
  });
  function visible(t) {
    if (filters.prio.size && !filters.prio.has(t.priority)) return false;
    if (filters.status.size && !filters.status.has(t.status)) return false;
    if (filters.flag.has('runnable') && !t.runnable) return false;
    if (filters.flag.has('human') && t.owner !== 'human') return false;
    const q = search.value.trim().toLowerCase();
    if (q && !(t.id.toLowerCase().includes(q) || t.title.toLowerCase().includes(q))) return false;
    return true;
  }
  function applyFilters() {
    const shown = new Set();
    tasks.forEach(t => {
      const ok = visible(t);
      nodeEls.get(t.id).classList.toggle('dim', !ok);
      if (ok) shown.add(t.id);
    });
    edgeEls.forEach(e => e.classList.toggle('dim',
      !shown.has(e.dataset.from) || !shown.has(e.dataset.to)));
  }

  // ── 可开跑清单 ──
  const ready = document.getElementById('ready');
  const readySorted = [...runnableTasks].sort((a, b) =>
    a.priority === b.priority ? a.id.localeCompare(b.id) : a.priority.localeCompare(b.priority));
  ready.innerHTML = '<b>可开跑（按优先级）：</b>' + (readySorted.length
    ? readySorted.map(t => `<a data-doc="${t.id}">${t.priority} · ${t.id} ${esc(t.title)}</a>`).join('')
    : '（无——先解锁依赖或验收进行中的任务）');
  ready.querySelectorAll('a').forEach(a =>
    a.addEventListener('click', () => selectTask(a.dataset.doc)));

  // ── 详情 ──
  const detail = document.getElementById('detail');
  function chip(text, cls) { return `<span class="pill ${cls || ''}">${text}</span>`; }
  function statusChip(s) {
    return `<span class="pill"><span class="dot" style="background:var(--st-${s.replace('_','-')})"></span>` +
      `${statusLabel[s]}</span>`;
  }
  function selectTask(id, center) {
    const t = byId.get(id);
    if (!t) return;
    nodeEls.forEach((el, nid) => el.classList.toggle('sel', nid === id));
    nodeEls.get(id).scrollIntoView(center ? { block: 'center', inline: 'center' }
                                          : { block: 'nearest', inline: 'nearest' });
    const chips = [statusChip(t.status), chip(t.priority), chip(ownerLabel[t.owner])];
    if (t.owner === 'agent') chips.push(chip(`model-tier: ${t.tier}`), chip(`effort: ${t.effort}`));
    if (t.runnable) chips.push(chip('可开跑'));
    if (t.checkpoint) chips.push(chip('下一检查点', 'ckpt'));
    if (t.manual === 'required') chips.push(chip('需人工验收'));
    const deps = t.deps.length
      ? t.deps.map(d => `<a href="#" class="doclink" data-doc="${d}">${d}</a>`).join('、') : '无';
    const adrsLine = t.adrs.length
      ? '<div class="meta">关联决策：' +
        t.adrs.map(a => `<a href="#" class="doclink" data-doc="${a}">${a}</a>`).join('、') + '</div>' : '';
    detail.innerHTML = `<h2>${t.id} ${esc(t.title)}</h2>` +
      `<div class="chips">${chips.join('')}</div>` +
      `<div class="meta">依赖：${deps} · 更新：${esc(t.updated)}` +
      (t.source ? ` · 来源：<code>${esc(t.source)}</code>` : '') + '</div>' + adrsLine + t.html;
    wireDoclinks(detail);
  }
  function selectAdr(id) {
    const a = adrById.get(id);
    if (!a) return;
    document.querySelectorAll('.adr-list li').forEach(li => {
      li.classList.toggle('sel', li.dataset.doc === id);
      if (li.dataset.doc === id) li.scrollIntoView({ block: 'nearest' });
    });
    const rel = [];
    if (a.supersedes.length) rel.push('取代 ' + a.supersedes.map(linkTo).join('、'));
    if (a.superseded_by.length) rel.push('被 ' + a.superseded_by.map(linkTo).join('、') + ' 取代');
    if (a.related.length) rel.push('相关 ' + a.related.map(linkTo).join('、'));
    adrDetail.innerHTML = `<h2>${a.id} ${esc(a.title)}</h2>` +
      `<div class="chips"><span class="pill">${adrStatusLabel[a.status]}</span>` +
      `<span class="pill">决策日 ${esc(a.date)}</span></div>` +
      (rel.length ? `<div class="meta">${rel.join(' · ')}</div>` : '') + a.html;
    wireDoclinks(adrDetail);
  }
  function linkTo(id) { return `<a href="#" class="doclink" data-doc="${id}">${id}</a>`; }
  function wireDoclinks(container) {
    container.querySelectorAll('a.doclink').forEach(a => a.addEventListener('click', ev => {
      ev.preventDefault();
      const id = a.dataset.doc;
      if (byId.has(id)) { showTab('tasks'); selectTask(id); }
      else if (adrById.has(id)) { showTab('adrs'); selectAdr(id); }
    }));
  }

  // ── ADR 列表 ──
  const adrList = document.getElementById('adr-list');
  const adrDetail = document.getElementById('adr-detail');
  adrs.forEach(a => {
    const li = document.createElement('li');
    li.dataset.doc = a.id;
    li.innerHTML = `<span class="aid">${a.id}</span><span class="atitle">${esc(a.title)}</span>` +
      `<span class="pill">${adrStatusLabel[a.status]}</span>`;
    li.addEventListener('click', () => selectAdr(a.id));
    adrList.appendChild(li);
  });
  if (!adrs.length) adrList.innerHTML = '<div class="empty">还没有 ADR</div>';

  // ── Tab ──
  const tabTasks = document.getElementById('tab-tasks'), tabAdrs = document.getElementById('tab-adrs');
  function showTab(which) {
    document.getElementById('view-tasks').hidden = which !== 'tasks';
    document.getElementById('view-adrs').hidden = which !== 'adrs';
    tabTasks.setAttribute('aria-selected', String(which === 'tasks'));
    tabAdrs.setAttribute('aria-selected', String(which === 'adrs'));
  }
  tabTasks.addEventListener('click', () => showTab('tasks'));
  tabAdrs.addEventListener('click', () => showTab('adrs'));

  if (checkpoint) selectTask(checkpoint.id);
})();
</script>
</body>
</html>
"""


# ───────────────────────── help ─────────────────────────

HELP_TEXT = """taskdag {version} — 仓库原生的 Task DAG + ADR 控制面（单文件，仅标准库）

事实源：docs/tasks/T-*.md 与 docs/adr/D-*.md 的 YAML frontmatter。
关系（depends_on / related_adrs / supersedes）只写 frontmatter，正文不重复。
status 只能用 transition 改；看板由 board 生成，不是编辑入口。

命令
  validate                          校验全部文档（schema、引用、状态机约束、依赖环）
  query k=v [k=v ...] [--json]      按 frontmatter 过滤；支持计算键 runnable=true|false
  transition <id> <status> [--reason 文字]
                                    状态迁移（写 status + updated，终态自动摘除
                                    human_checkpoint，并在 ## 执行记录 追加一行）
  new task --title 标题 [--owner agent|human] [--model-tier ...] [--effort ...]
           [--priority p0|p1|p2] [--manual none|required]
           [--deps T-001,T-002] [--adrs D-001]
  new adr --title 标题
  board                             生成 {board}
                                    （校验不过不生成；BOARD_FILE 常量可为绝对路径，
                                    把看板发布到仓库外）
  help                              本说明

Task frontmatter（唯一事实源）
  type: task            固定
  id: T-001             与文件名一致，编号只增不复用
  title / status / updated
  priority: p0|p1|p2    p0=当前周期必经；p1=下一里程碑/发布窗口前必须；p2=机会性
  owner: agent|human    human 任务不写 model-tier/effort
  model-tier: high|mid  规划用的模型档位（派发时映射到当天的具体模型/CLI）
  effort: mid|high|xhigh|max
  manual_acceptance: none|required
  human_checkpoint: next   全仓最多一个；须 manual_acceptance: required
  depends_on: []        依赖的任务 id 列表；runnable = planned 且依赖全 done
  related_adrs / source / area / phase   可选

Task 正文固定五节（各恰好一节且非空）：
  ## 启动条件 / ## 目标 / ## 交付物 / ## 验收与证据（内含唯一 ### 人工验收）/ ## 非目标
  可选 ## 执行记录（transition 自动追加，最新在上）。
  manual_acceptance: none → 人工验收小节只写「无。」
  manual_acceptance: required → 恰好一条「- 最小动作：…」与一条「- 通过标准：…」

状态机
  planned → in_progress | blocked | cancelled
  in_progress → review | blocked | cancelled
  review → in_progress | done | blocked | cancelled
  blocked → planned | in_progress | cancelled     （done / cancelled 为终态）
  blocked 只用于外部条件或缺决策，不用于普通未满足依赖（那是 planned 未 runnable）。

ADR frontmatter：type: adr / id: D-001 / title / status（proposed|accepted|
  deprecated|superseded|rejected）/ date（决策日）/ updated /
  supersedes / superseded_by（须互相声明）/ related_adrs / area / source
ADR 正文至少 ## 背景 与 ## 决策 各一节。改核心取舍开新编号并互链 supersede，
小澄清直接更新原文。

粒度：一个任务 = 一次可交给单个 agent 的派发（一个上下文窗口内可完成、
验收可独立判定）。更大的事拆成多个任务连成 DAG。

任务 vs 目标：任务是可执行、可验收的动作；**目标（结果指标，如「本周真实
生成 ≥ N 次」）不建任务**——目标放专门的目标文档，任务用 source 指向它，
看板用 BOARD_NOTE 常量把当前目标显示在头部。持续职责可作为长期 in_progress
任务；acceptance-only 的人工检查点（过一遍就绪清单）是合法任务。
"""


# ───────────────────────── main ─────────────────────────


def main():
    parser = argparse.ArgumentParser(prog="taskdag", add_help=False)
    parser.add_argument("--version", action="version", version=f"taskdag {VERSION}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("validate")
    q = sub.add_parser("query")
    q.add_argument("filters", nargs="*")
    q.add_argument("--json", action="store_true")
    t = sub.add_parser("transition")
    t.add_argument("id")
    t.add_argument("status")
    t.add_argument("--reason")
    n = sub.add_parser("new")
    n.add_argument("kind", choices=["task", "adr"])
    n.add_argument("--title", required=True)
    n.add_argument("--owner", choices=OWNERS, default="agent")
    n.add_argument("--model-tier", dest="tier", choices=MODEL_TIERS)
    n.add_argument("--effort", choices=EFFORTS)
    n.add_argument("--manual", choices=MANUAL_ACCEPTANCE, default="none")
    n.add_argument("--priority", choices=PRIORITIES, default="p2")
    n.add_argument("--deps", default="")
    n.add_argument("--adrs", default="")
    sub.add_parser("board")
    sub.add_parser("help")
    args = parser.parse_args()

    if args.command in (None, "help"):
        print(HELP_TEXT.format(version=VERSION, board=BOARD_FILE))
        return
    if args.command == "validate":
        errors = validate(load_all())
        if errors:
            for error in errors:
                print(error)
            sys.exit(1)
        docs = load_all()
        print(f"OK: {len(adrs_of(docs))} ADRs, {len(tasks_of(docs))} tasks, DAG acyclic")
        return
    if args.command == "query":
        filters = {}
        for pair in args.filters:
            if "=" not in pair:
                sys.exit(f"error: filter must be key=value, got {pair!r}")
            key, _, value = pair.partition("=")
            filters[key] = value
        query(load_all(), filters, as_json=args.json)
        return
    if args.command == "transition":
        transition(args.id, args.status, args.reason)
        return
    if args.command == "new":
        deps = [d.strip() for d in args.deps.split(",") if d.strip()]
        adrs = [a.strip() for a in args.adrs.split(",") if a.strip()]
        new_doc(args.kind, args.title, args.owner, args.tier, args.effort,
                args.manual, deps, adrs, args.priority)
        return
    if args.command == "board":
        board()
        return


if __name__ == "__main__":
    main()
