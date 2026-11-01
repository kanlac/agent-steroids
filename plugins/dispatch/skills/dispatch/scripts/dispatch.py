#!/usr/bin/env python3
"""dispatch.py — one dispatcher + live board for coding-agent CLIs.

Standard library only.  Three subcommands:

  dispatch.py run    --name ... --agent codex|agy|cmd ...
  dispatch.py status
  dispatch.py board   [--port 8765]

Each run writes its event stream, final reply, session id and exit code into
the task directory, and one line per start / end into the runs file
($DISPATCH_RUNS, default $DISPATCH_ROOT/runs.jsonl). Task directories without a
runs record (older runs) are found by scanning $DISPATCH_ROOT.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = Path(os.environ.get("DISPATCH_ROOT", str(Path.home() / ".local/state/dispatch")))
RUNS_FILE = Path(os.environ.get("DISPATCH_RUNS", str(DEFAULT_ROOT / "runs.jsonl")))
PRICES_FILE = Path(os.environ.get("DISPATCH_PRICES", str(APP_DIR / "prices.json")))
REFRESH_SECONDS = 10
LEGACY_STALE_SECONDS = 180

# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

_COMPOSERS = [
    "巴赫", "莫扎特", "贝多芬", "勃拉姆斯", "肖邦", "德彪西", "拉威尔", "斯特拉文斯基",
    "马勒", "舒伯特", "舒曼", "李斯特", "瓦格纳", "威尔第", "普契尼", "海顿",
    "亨德尔", "维瓦尔第", "柴可夫斯基", "拉赫玛尼诺夫", "普罗科菲耶夫", "肖斯塔科维奇",
    "巴托克", "科普兰", "格什温", "艾灵顿", "伯恩斯坦", "萨蒂", "福雷", "圣桑",
    "德沃夏克", "西贝柳斯", "格里格", "比才", "柏辽兹", "蒙特威尔第", "普赛尔", "泰勒曼",
    "斯卡拉蒂", "帕格尼尼", "布鲁克纳", "霍尔斯特", "沃恩-威廉斯", "布里顿", "埃尔加",
    "雅纳切克", "柯达伊", "利盖蒂", "梅西安", "布列兹", "施托克豪森", "凯奇", "赖希",
    "格拉斯", "亚当斯", "佩尔特", "塔文纳", "惠特克", "武满彻", "尹伊桑", "劳塔瓦拉",
    "巴伯", "艾夫斯", "卡特", "费尔德曼", "布朗", "泽纳基斯", "瓦雷兹", "考威尔",
    "南卡罗", "安太尔", "奥尔夫", "欣德米特", "魏尔", "克热内克", "策姆林斯基",
    "贝尔格", "韦伯恩", "勋伯格", "沃尔夫", "多赫南伊", "米约", "奥涅格", "普朗克",
]


def alias_for(task_dir: Path) -> str:
    """Stable pseudonym for a task directory.  Same dir -> same alias, forever."""
    key = str(Path(task_dir).expanduser().resolve())
    h = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16)
    return f"{_COMPOSERS[h % len(_COMPOSERS)]}·{h // len(_COMPOSERS) % 100:02d}"


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def parse_iso(value):
    if not value:
        return None
    try:
        d = dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if d.tzinfo is None:
        d = d.astimezone()
    return d


def fmt_duration(seconds) -> str:
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    if seconds < 86400:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    return f"{seconds // 86400}d{(seconds % 86400) // 3600:02d}h"


def fmt_ago(seconds) -> str:
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s前"
    if seconds < 3600:
        return f"{seconds // 60}m前"
    if seconds < 86400:
        return f"{seconds // 3600}h前"
    return f"{seconds // 86400}d前"


def fmt_tokens(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "—"
    if n >= 1_000_000_000:
        return f"{n / 1e9:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1e6:.2f}M"
    if n >= 1_000:
        return f"{n / 1e3:.1f}k"
    return str(n)


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(text))


def trunc(text: str, width: int) -> str:
    text = str(text)
    if display_width(text) <= width:
        return text
    out = ""
    w = 0
    for ch in text:
        cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if w + cw > width - 1:
            break
        out += ch
        w += cw
    return out + "…"


def pad(text: str, width: int) -> str:
    return str(text) + " " * max(0, width - display_width(str(text)))


def norm_path(p) -> str:
    return str(Path(p).expanduser().resolve())


# ---------------------------------------------------------------------------
# usage normalisation
#   input   = non-cached prompt tokens
#   cached  = cache-read tokens
#   output  = completion tokens
#   reasoning = reasoning/thinking tokens (subset of output, kept separately)
# ---------------------------------------------------------------------------

def u_empty():
    return {"input": 0, "cached": 0, "output": 0, "reasoning": 0}


def u_add(dst, src):
    for k in dst:
        dst[k] += int((src or {}).get(k) or 0)
    return dst


def u_final(u):
    out = u_empty()
    u_add(out, u or {})
    out["total"] = out["input"] + out["cached"] + out["output"]
    return out


def _int(v):
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def usage_codex(raw):
    raw = raw or {}
    inp = _int(raw.get("input_tokens"))
    cached = _int(raw.get("cached_input_tokens"))
    return {
        "input": max(0, inp - cached),
        "cached": cached,
        "output": _int(raw.get("output_tokens")),
        "reasoning": _int(raw.get("reasoning_output_tokens")),
    }


def usage_agy(raw):
    raw = raw or {}
    return {
        "input": _int(raw.get("input_tokens")),
        "cached": _int(raw.get("cache_read_tokens")),
        "output": _int(raw.get("output_tokens")),
        "reasoning": _int(raw.get("thinking_tokens")),
    }


def usage_cmd(raw):
    raw = raw or {}
    inp = _int(raw.get("inputTokens"))
    cached = _int(raw.get("cacheReadTokens"))
    return {
        "input": max(0, inp - cached),
        "cached": cached,
        "output": _int(raw.get("outputTokens")),
        "reasoning": 0,
    }


# ---------------------------------------------------------------------------
# adapters
# ---------------------------------------------------------------------------

class Adapter:
    key = "base"
    default_model = ""
    default_effort = None
    retry_sleep = 60
    max_retries = 0
    merge_stderr = False
    EV_RE = re.compile(r"$^")  # no files

    # ---- naming ----------------------------------------------------------
    def event_files(self, task_dir: Path):
        files = []
        for p in Path(task_dir).glob("events*.jsonl"):
            if self.EV_RE.match(p.name):
                files.append(p)
        return sorted(files, key=lambda p: int(self.EV_RE.match(p.name).group(1)))

    def event_index(self, task_dir: Path) -> int:
        return len(self.event_files(Path(task_dir)))

    def event_path(self, task_dir: Path, n: int) -> Path:
        return Path(task_dir) / f"events-{n}.jsonl"

    def result_path(self, task_dir: Path, n: int) -> Path:
        return Path(task_dir) / f"result-{n}.md"

    def stderr_path(self, task_dir: Path, n: int) -> Path:
        return Path(task_dir) / f"stderr-{n}.txt"

    def session_path(self, task_dir: Path) -> Path:
        return Path(task_dir) / "session.txt"

    def exit_path(self, task_dir: Path) -> Path:
        return Path(task_dir) / "exit.txt"

    # ---- accumulator -----------------------------------------------------
    def new_acc(self):
        return {
            "session": None,
            "final_usage": None,
            "partial": u_empty(),
            "status_raw": None,
            "has_result": False,
            "has_result_line": False,
            "done": False,
            "flags": set(),
            "model": None,
            "cwd": None,
            "result_text": None,
            "lines": 0,
        }

    def _flags_from_text(self, acc, text):
        low = (text or "").lower()
        if "at capacity" in low:
            acc["flags"].add("capacity")
        if "max turns" in low or "max_turns" in low or "max-turns" in low:
            acc["flags"].add("max_turns")

    def consume(self, acc, raw):
        raw = raw.rstrip("\r\n")
        if not raw.strip():
            return acc
        acc["lines"] += 1
        self._flags_from_text(acc, raw)
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            obj = None
        self.feed(acc, obj, raw)
        return acc

    def feed(self, acc, obj, raw):
        raise NotImplementedError

    def usage(self, acc):
        u = acc["final_usage"] if acc["final_usage"] is not None else acc["partial"]
        return u_final(u)

    def classify(self, acc, rc):
        if rc is not None and rc < 0:
            return "killed"
        if "capacity" in acc["flags"]:
            return "capacity"
        if "max_turns" in acc["flags"]:
            return "max_turns"
        if acc["done"] or acc["has_result"]:
            if str(acc["status_raw"] or "").lower() in ("error", "failed", "failure"):
                return "failed"
            return "ok" if rc in (0, None) else "failed"
        return "no_result" if rc in (0, None) else "failed"

    def auto_resume(self, acc, rc, ctx):
        return None

    def build_command(self, *, prompt, model, effort, resume, event_path, result_path):
        raise NotImplementedError


class CodexAdapter(Adapter):
    key = "codex"
    default_model = "gpt-6.1-sol"
    default_effort = "high"
    retry_sleep = 120
    max_retries = 6
    merge_stderr = True
    EV_RE = re.compile(r"^events-(\d+)\.jsonl$")

    def feed(self, acc, obj, raw):
        if obj is None:
            return
        t = obj.get("type")
        if t == "thread.started":
            acc["session"] = obj.get("thread_id") or acc["session"]
        elif t == "turn.completed":
            acc["final_usage"] = usage_codex(obj.get("usage"))
            acc["status_raw"] = "completed"
            acc["has_result"] = True
            acc["done"] = True
        elif t in ("turn.failed", "error"):
            msg = ""
            if isinstance(obj.get("message"), str):
                msg = obj["message"]
            if isinstance(obj.get("error"), dict):
                msg += " " + str(obj["error"].get("message") or "")
            self._flags_from_text(acc, msg)
            acc["flags"].add("failed")
            acc["status_raw"] = "error"
            acc["done"] = True
        elif t == "item.completed":
            item = obj.get("item") or {}
            if item.get("type") == "agent_message" and item.get("text"):
                acc["result_text"] = item["text"]

    def classify(self, acc, rc):
        if rc is not None and rc < 0:
            return "killed"
        if "capacity" in acc["flags"]:
            return "capacity"
        if "max_turns" in acc["flags"]:
            return "max_turns"
        if acc["done"] and acc["status_raw"] == "completed":
            return "ok" if rc == 0 else "failed"
        if rc == 0:
            return "no_result"
        return "failed"

    def auto_resume(self, acc, rc, ctx):
        if rc != 0 and acc["session"] and "capacity" in acc["flags"] and ctx["attempt"] < ctx["max_attempts"]:
            return {
                "reason": "capacity",
                "session": acc["session"],
                "delay": ctx["delay"],
                "prompt": "（自动续跑）上一轮因模型服务 at capacity 中断，不是你的问题。请从中断处继续原任务，不要重做已完成的步骤。",
            }
        return None

    def build_command(self, *, prompt, model, effort, resume, event_path, result_path):
        binary = os.environ.get("DISPATCH_CODEX_BIN") or "codex"
        cmd = [binary]
        top = os.environ.get("CODEX_TOP")
        if top:
            cmd.extend(shlex.split(top))
        cmd.append("exec")
        if resume:
            cmd.extend(["resume", str(resume)])
        cmd.extend([
            "-m", model or self.default_model,
            "-c", f"model_reasoning_effort={effort or self.default_effort}",
            "-c", "service_tier=default",
            "-o", str(result_path),
            "--json",
            prompt,
        ])
        return cmd


class AgyAdapter(Adapter):
    key = "agy"
    default_model = "gemini-4-argon-medium"
    merge_stderr = False
    EV_RE = re.compile(r"^events-agy-(\d+)\.jsonl$")

    def event_path(self, task_dir, n):
        return Path(task_dir) / f"events-agy-{n}.jsonl"

    def result_path(self, task_dir, n):
        return Path(task_dir) / f"result-agy-{n}.md"

    def stderr_path(self, task_dir, n):
        return Path(task_dir) / f"stderr-agy-{n}.txt"

    def session_path(self, task_dir):
        return Path(task_dir) / "session-agy.txt"

    def exit_path(self, task_dir):
        return Path(task_dir) / "exit-agy.txt"

    def feed(self, acc, obj, raw):
        if obj is None:
            return
        ev = obj.get("event")
        if ev == "init":
            acc["session"] = obj.get("conversation_id") or acc["session"]
            init = obj.get("init") or {}
            acc["model"] = init.get("model") or acc["model"]
            acc["cwd"] = init.get("cwd") or acc["cwd"]
        elif ev == "step_update":
            su = obj.get("step_update") or {}
            acc["session"] = su.get("conversation_id") or acc["session"]
            if su.get("step_type") == "agent_response" and su.get("usage"):
                u_add(acc["partial"], usage_agy(su["usage"]))
        elif ev == "result":
            r = obj.get("result") or {}
            acc["session"] = r.get("conversation_id") or acc["session"]
            acc["status_raw"] = r.get("status")
            acc["final_usage"] = usage_agy(r.get("usage"))
            acc["result_text"] = r.get("response")
            acc["has_result"] = True
            acc["done"] = True

    def classify(self, acc, rc):
        if rc is not None and rc < 0:
            return "killed"
        if "capacity" in acc["flags"]:
            return "capacity"
        if not acc["has_result"]:
            return "no_result" if rc in (0, None) else "failed"
        if str(acc["status_raw"] or "").upper() in ("SUCCESS", "OK", "COMPLETED"):
            return "ok" if rc in (0, None) else "failed"
        return "failed"

    def build_command(self, *, prompt, model, effort, resume, event_path, result_path):
        binary = os.environ.get("DISPATCH_AGY_BIN") or "agy"
        cmd = [
            binary, "-p", prompt,
            "--model", model or self.default_model,
            "--dangerously-skip-permissions",
            "--output-format", "stream-json",
            "--print-timeout", "0",
        ]
        if resume:
            cmd.extend(["--conversation", str(resume)])
        return cmd


class CmdAdapter(Adapter):
    key = "cmd"
    default_model = "deepseek/deepseek-v4.1-flash"
    retry_sleep = 60
    max_retries = 3
    merge_stderr = False
    EV_RE = re.compile(r"^events-cmd-(\d+)\.jsonl$")

    def event_path(self, task_dir, n):
        return Path(task_dir) / f"events-cmd-{n}.jsonl"

    def result_path(self, task_dir, n):
        return Path(task_dir) / f"result-cmd-{n}.md"

    def stderr_path(self, task_dir, n):
        return Path(task_dir) / f"stderr-cmd-{n}.txt"

    def session_path(self, task_dir):
        return Path(task_dir) / "session-cmd.txt"

    def exit_path(self, task_dir):
        return Path(task_dir) / "exit-cmd.txt"

    def feed(self, acc, obj, raw):
        if obj is None:
            return
        t = obj.get("type")
        if t == "result":
            r = obj
            acc["session"] = r.get("sessionId") or acc["session"]
            acc["status_raw"] = r.get("subtype") or r.get("stopReason")
            acc["final_usage"] = usage_cmd(r.get("usage"))
            acc["result_text"] = r.get("finalText")
            acc["has_result"] = True
            acc["has_result_line"] = True
            acc["done"] = True
            if str(acc["status_raw"]).lower() == "max_turns":
                acc["flags"].add("max_turns")
        elif t == "event":
            ev = obj.get("event") or {}
            et = ev.get("type")
            sid = ev.get("sessionId")
            if sid:
                acc["session"] = sid
            if et == "run_start":
                acc["session"] = ev.get("sessionId") or acc["session"]
            elif et == "model_request_start":
                if ev.get("model"):
                    acc["model"] = ev["model"]
            elif et == "turn_end":
                u_add(acc["partial"], usage_cmd(ev.get("usage")))
            elif et == "run_end":
                r = ev.get("result") or {}
                acc["session"] = r.get("sessionId") or (r.get("nextState") or {}).get("sessionId") or acc["session"]
                if r.get("cwd"):
                    acc["cwd"] = r["cwd"]
                if r.get("usage"):
                    acc["final_usage"] = usage_cmd(r["usage"])
                if r.get("stopReason"):
                    acc["status_raw"] = r["stopReason"]
                    if str(r["stopReason"]).lower() == "max_turns":
                        acc["flags"].add("max_turns")
                if r.get("finalText"):
                    acc["result_text"] = r["finalText"]
                acc["done"] = True

    def classify(self, acc, rc):
        if rc is not None and rc < 0:
            return "killed"
        if "capacity" in acc["flags"]:
            return "capacity"
        if "max_turns" in acc["flags"] or str(acc["status_raw"] or "").lower() == "max_turns":
            return "max_turns"
        if not acc["has_result_line"]:
            if rc in (126, 127):
                return "failed"
            return "no_result"
        st = str(acc["status_raw"] or "").lower()
        if st in ("success", "end_turn", "stop"):
            return "ok" if rc in (0, None) else "failed"
        return "failed"

    def auto_resume(self, acc, rc, ctx):
        if not acc["has_result_line"] and acc["session"] and ctx["attempt"] < ctx["max_attempts"]:
            return {
                "reason": "no_result",
                "session": acc["session"],
                "delay": ctx["delay"],
                "prompt": "（自动续跑）上一轮在模型请求中途意外结束，不是你的问题。请从中断处继续原任务，不要重做已完成的步骤。",
            }
        return None

    def build_command(self, *, prompt, model, effort, resume, event_path, result_path):
        binary = os.environ.get("DISPATCH_CMD_BIN") or "cmd"
        cmd = [
            binary, "-p", prompt,
            "-m", model or self.default_model,
            "--yolo", "--trust", "--skip-onboarding", "--no-auto-update",
            "--output-format", "json", "--max-turns", "1500",
        ]
        if effort:
            cmd.extend(["--effort", effort])
        if resume:
            cmd.extend(["--resume", str(resume)])
        return cmd


ADAPTERS = {a.key: a for a in (CodexAdapter(), AgyAdapter(), CmdAdapter())}

# Derived from the registry: adding an adapter automatically teaches the
# legacy scanner about that agent's event-file names.
LEGACY_PATTERNS = [(a.key, a.EV_RE) for a in ADAPTERS.values() if a.EV_RE.pattern != r"$^"]


# ---------------------------------------------------------------------------
# incremental event-file readers
# ---------------------------------------------------------------------------

class FileReader:
    def __init__(self, path: Path, adapter: Adapter, tail_bytes=None):
        self.path = Path(path)
        self.adapter = adapter
        self.tail_bytes = tail_bytes
        self.reset()

    def reset(self):
        self.acc = self.adapter.new_acc()
        self.offset = 0
        self.buf = b""
        self.inode = None
        self.size = -1
        self.mtime = 0
        self.birth = 0

    def refresh(self):
        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            return self.acc
        if self.inode != st.st_ino or st.st_size < self.offset:
            self.reset()
        if self.inode == st.st_ino and st.st_size == self.size and st.st_mtime == self.mtime:
            return self.acc

        first = self.inode is None
        try:
            with open(self.path, "rb") as f:
                if first and self.tail_bytes and st.st_size > self.tail_bytes:
                    f.seek(st.st_size - self.tail_bytes)
                    chunk = f.read()
                    nl = chunk.find(b"\n")
                    chunk = chunk[nl + 1:] if nl >= 0 else b""
                    self.offset = st.st_size
                else:
                    f.seek(self.offset)
                    chunk = f.read()
                    self.offset = st.st_size
        except OSError:
            return self.acc

        self.inode = st.st_ino
        self.size = st.st_size
        self.mtime = st.st_mtime
        self.birth = getattr(st, "st_birthtime", st.st_mtime) or st.st_mtime

        if self.buf:
            chunk = self.buf + chunk
            self.buf = b""
        if not chunk:
            return self.acc
        lines = chunk.split(b"\n")
        if not chunk.endswith(b"\n"):
            self.buf = lines.pop()
        for raw in lines:
            self.adapter.consume(self.acc, raw.decode("utf-8", "replace"))
        return self.acc


_CACHE = {}
_CACHE_LOCK = threading.Lock()


def read_event_file(path: Path, adapter: Adapter, *, mode="full", cache=None):
    tail = None if mode == "full" else 256 * 1024
    key = (str(path), mode)
    if cache is None:
        reader = FileReader(path, adapter, tail)
    else:
        reader = cache.get(key)
        if reader is None:
            reader = FileReader(path, adapter, tail)
            cache[key] = reader
    return reader.refresh(), reader


def combine_files(files, adapter: Adapter, *, mode="full", cache=None):
    total = u_empty()
    session = None
    model = None
    cwd = None
    last_acc = None
    last_path = None
    last_mtime = 0
    earliest = None
    for p in files:
        acc, reader = read_event_file(Path(p), adapter, mode=mode, cache=cache)
        u_add(total, adapter.usage(acc))
        session = session or acc["session"]
        model = model or acc["model"]
        cwd = cwd or acc["cwd"]
        last_acc = acc
        last_path = Path(p)
        last_mtime = max(last_mtime, reader.mtime or 0)
        b = reader.birth or reader.mtime or 0
        earliest = b if earliest is None else min(earliest, b)
    return {
        "usage": u_final(total),
        "session": session,
        "model": model,
        "cwd": cwd,
        "acc": last_acc,
        "last_path": last_path,
        "last_mtime": last_mtime,
        "earliest": earliest,
    }


# ---------------------------------------------------------------------------
# ledger
# ---------------------------------------------------------------------------

def append_json(path: Path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def read_runs(path=None):
    path = Path(path or RUNS_FILE)
    if not path.exists():
        return []
    records = {}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            rid = obj.get("run_id")
            if not rid:
                continue
            rec = records.setdefault(rid, {"run_id": rid})
            rec.update(obj)
    return sorted(records.values(), key=lambda r: str(r.get("started_at") or ""))


def read_exit(adapter: Adapter, task_dir: Path):
    p = adapter.exit_path(task_dir)
    try:
        return int(p.read_text().strip())
    except (OSError, ValueError):
        return None


def read_session_file(adapter: Adapter, task_dir: Path):
    p = adapter.session_path(task_dir)
    try:
        return p.read_text().strip() or None
    except OSError:
        return None


def looks_active(files, run_start_ts):
    out = []
    for p in files:
        try:
            st = p.stat()
        except OSError:
            continue
        born = getattr(st, "st_birthtime", st.st_mtime) or st.st_mtime
        if max(st.st_mtime, born) >= run_start_ts - 5:
            out.append(p)
    return out


def active_files(rec):
    adapter = ADAPTERS.get(rec.get("agent"))
    if not adapter:
        return []
    start = parse_iso(rec.get("started_at"))
    if start is None:
        return []
    td = Path(rec.get("task_dir") or ".")
    return looks_active(adapter.event_files(td), start.timestamp())


def usage_from_end_record(rec):
    u = rec.get("usage") or {}
    return u_final({
        "input": _int(u.get("input")),
        "cached": _int(u.get("cached")),
        "output": _int(u.get("output")),
        "reasoning": _int(u.get("reasoning")),
    })


def load_prices():
    try:
        data = json.loads(PRICES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if not str(k).startswith("_") and isinstance(v, dict)}


def cost_of(usage, model, prices):
    if not model:
        return None
    p = prices.get(model)
    if not p:
        return None
    try:
        return (
            usage.get("input", 0) / 1_000_000 * float(p.get("input", 0))
            + usage.get("cached", 0) / 1_000_000 * float(p.get("cached", 0))
            + usage.get("output", 0) / 1_000_000 * float(p.get("output", 0))
        )
    except (TypeError, ValueError):
        return None


def row_for_run(rec, prices, cache=None):
    adapter = ADAPTERS.get(rec.get("agent")) or ADAPTERS["codex"]
    started = parse_iso(rec.get("started_at"))
    ended = parse_iso(rec.get("ended_at"))
    now = time.time()
    running = not rec.get("ended_at")

    if running:
        files = active_files(rec)
        combined = combine_files(files, adapter, mode="full", cache=cache) if files else None
        usage = combined["usage"] if combined else u_final({})
        status = "running" if files else "starting"
        session = (combined or {}).get("session") or rec.get("session")
        model = (combined or {}).get("model") or rec.get("model")
        cwd = rec.get("cwd") or (combined or {}).get("cwd")
        last_epoch = (combined or {}).get("last_mtime") or (started.timestamp() if started else now)
        events = [str(p) for p in files]
        elapsed = now - started.timestamp() if started else None
        retries = rec.get("retries") or 0
    else:
        files = [Path(p) for p in (rec.get("events_files") or [])]
        usage = usage_from_end_record(rec)
        status = rec.get("status") or "ok"
        session = rec.get("session")
        model = rec.get("model")
        cwd = rec.get("cwd")
        end_ts = ended.timestamp() if ended else now
        last_epoch = end_ts
        for p in files:
            try:
                last_epoch = max(last_epoch, p.stat().st_mtime)
            except OSError:
                pass
        events = [str(p) for p in files]
        elapsed = (ended.timestamp() - started.timestamp()) if (ended and started) else None
        retries = rec.get("retries") or 0

    last_dt = dt.datetime.fromtimestamp(last_epoch).astimezone() if last_epoch else None
    return {
        "run_id": rec.get("run_id"),
        "name": rec.get("name") or "—",
        "alias": rec.get("alias") or alias_for(Path(rec.get("task_dir") or ".")),
        "agent": rec.get("agent"),
        "model": model or rec.get("model"),
        "effort": rec.get("effort"),
        "status": status,
        "started_at": rec.get("started_at"),
        "ended_at": rec.get("ended_at"),
        "elapsed_seconds": elapsed,
        "last_activity_at": last_dt.isoformat(timespec="seconds") if last_dt else None,
        "last_activity_ago": max(0, now - last_epoch) if last_epoch else None,
        "usage": usage,
        "cost_usd": cost_of(usage, model or rec.get("model"), prices),
        "task_dir": rec.get("task_dir"),
        "cwd": cwd,
        "session": session,
        "retries": retries,
        "legacy": False,
        "events_files": events,
    }


# ---------------------------------------------------------------------------
# legacy scan
# ---------------------------------------------------------------------------

def scan_legacy(root=None, *, exclude_pairs=None, cache=None, prices=None):
    root = Path(root or DEFAULT_ROOT)
    prices = prices or load_prices()
    exclude_pairs = exclude_pairs or set()
    rows = []
    if not root.is_dir():
        return rows
    now = time.time()
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        groups = {}
        try:
            entries = list(d.glob("events*.jsonl"))
        except OSError:
            continue
        for p in entries:
            for key, rx in LEGACY_PATTERNS:
                if rx.match(p.name):
                    groups.setdefault(key, []).append(p)
                    break
        for key, files in groups.items():
            if (norm_path(d), key) in exclude_pairs:
                continue
            adapter = ADAPTERS[key]
            files.sort(key=lambda p: int(adapter.EV_RE.match(p.name).group(1)))
            combined = combine_files(files, adapter, mode="tail", cache=cache)
            acc = combined["acc"] or adapter.new_acc()
            latest = files[-1]
            try:
                latest_mtime = latest.stat().st_mtime
            except OSError:
                latest_mtime = combined["last_mtime"] or now
            exit_path = adapter.exit_path(d)
            try:
                exit_mtime = exit_path.stat().st_mtime
            except OSError:
                exit_mtime = 0
            rc = read_exit(adapter, d)

            if latest_mtime > exit_mtime + 1 and now - latest_mtime < LEGACY_STALE_SECONDS:
                status = "running"
            elif rc is not None:
                status = adapter.classify(acc, rc)
            elif acc["done"] or acc["has_result"]:
                status = adapter.classify(acc, 0)
            elif now - latest_mtime < LEGACY_STALE_SECONDS:
                status = "running"
            else:
                status = "no_result"

            start_epoch = combined["earliest"] or latest_mtime
            elapsed = (now if status in ("running", "starting") else latest_mtime) - start_epoch
            session = combined["session"] or read_session_file(adapter, d)
            model = combined["model"]
            usage = combined["usage"]
            last_dt = dt.datetime.fromtimestamp(latest_mtime).astimezone()
            rows.append({
                "run_id": None,
                "name": d.name,
                "alias": alias_for(d),
                "agent": key,
                "model": model,
                "effort": None,
                "status": status,
                "started_at": dt.datetime.fromtimestamp(start_epoch).astimezone().isoformat(timespec="seconds"),
                "ended_at": None if status == "running" else last_dt.isoformat(timespec="seconds"),
                "elapsed_seconds": max(0, elapsed),
                "last_activity_at": last_dt.isoformat(timespec="seconds"),
                "last_activity_ago": max(0, now - latest_mtime),
                "usage": usage,
                "cost_usd": cost_of(usage, model, prices),
                "task_dir": str(d),
                "cwd": combined["cwd"],
                "session": session,
                "retries": 0,
                "legacy": True,
                "events_files": [str(p) for p in files],
            })
    return rows


# ---------------------------------------------------------------------------
# board data
# ---------------------------------------------------------------------------

def build_data(root=None, runs_file=None):
    prices = load_prices()
    runs = read_runs(runs_file or RUNS_FILE)
    with _CACHE_LOCK:
        rows = [row_for_run(r, prices, cache=_CACHE) for r in runs]
        exclude = {(norm_path(r.get("task_dir") or ""), r.get("agent")) for r in runs if r.get("task_dir")}
        legacy = scan_legacy(root, exclude_pairs=exclude, cache=_CACHE, prices=prices)

    all_rows = rows + legacy
    running = sum(1 for r in all_rows if r["status"] in ("running", "starting"))
    by_agent = {}
    for r in all_rows:
        a = r.get("agent") or "other"
        slot = by_agent.setdefault(a, {"tokens": 0, "runs": 0, "running": 0})
        slot["tokens"] += int(r["usage"].get("total") or 0)
        slot["runs"] += 1
        if r["status"] in ("running", "starting"):
            slot["running"] += 1

    total_tokens = sum(int(r["usage"].get("total") or 0) for r in all_rows)
    total_elapsed = sum(float(r.get("elapsed_seconds") or 0) for r in all_rows)
    costs = [r["cost_usd"] for r in all_rows if r.get("cost_usd") is not None]
    return {
        "generated_at": now_iso(),
        "root": str(root or DEFAULT_ROOT),
        "runs_file": str(runs_file or RUNS_FILE),
        "refresh_seconds": REFRESH_SECONDS,
        "runs": rows,
        "legacy": legacy,
        "summary": {
            "running": running,
            "run_count": len(rows),
            "legacy_count": len(legacy),
            "total_tokens": total_tokens,
            "total_elapsed_seconds": total_elapsed,
            "total_cost_usd": sum(costs) if costs else None,
            "priced_rows": len(costs),
            "by_agent": by_agent,
            "prices_loaded": bool(prices),
        },
    }


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

class Terminated(Exception):
    pass


_CURRENT = {"proc": None}


def _on_signal(signum, frame):
    proc = _CURRENT.get("proc")
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
        except OSError:
            pass
    raise Terminated()


def execute(cmd, cwd, event_path: Path, stderr_path: Path, merge_stderr: bool):
    event_path.parent.mkdir(parents=True, exist_ok=True)
    out = open(event_path, "wb")
    err = None
    try:
        if not merge_stderr:
            err = open(stderr_path, "wb")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=(subprocess.STDOUT if merge_stderr else err),
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            out.write(f"dispatch: cannot start {cmd[0]!r}: {exc}\n".encode("utf-8"))
            out.flush()
            return 127
        _CURRENT["proc"] = proc
        try:
            return proc.wait()
        except Terminated:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    proc.kill()
                except OSError:
                    pass
                proc.wait()
            raise
        finally:
            _CURRENT["proc"] = None
    finally:
        out.close()
        if err is not None:
            err.close()


def parse_one_file(path: Path, adapter: Adapter):
    acc, reader = read_event_file(path, adapter, mode="full", cache=None)
    return acc, reader


def write_result(adapter: Adapter, task_dir: Path, out_path: Path, acc):
    if adapter.key == "codex":
        if out_path.exists():
            try:
                shutil.copyfile(out_path, task_dir / "result.md")
            except OSError:
                pass
        elif acc.get("result_text"):
            try:
                out_path.write_text(acc["result_text"], encoding="utf-8")
                shutil.copyfile(out_path, task_dir / "result.md")
            except OSError:
                pass
    else:
        if acc.get("result_text") is not None:
            try:
                out_path.write_text(acc["result_text"], encoding="utf-8")
            except OSError:
                pass


def find_cmd_cwd(session, task_dir: Path, runs_file=None):
    if not session:
        return None
    for rec in read_runs(runs_file):
        if rec.get("agent") == "cmd" and rec.get("session") == session and rec.get("cwd"):
            return rec["cwd"]
    adapter = ADAPTERS["cmd"]
    for p in reversed(adapter.event_files(Path(task_dir))):
        acc, _ = parse_one_file(p, adapter)
        if acc.get("session") == session and acc.get("cwd"):
            return acc["cwd"]
    return None


def resolve_resume(adapter: Adapter, task_dir: Path, resume, cwd: Path, runs_file=None):
    if not resume:
        return None, cwd, False
    if resume == "auto":
        sid = read_session_file(adapter, task_dir)
        if not sid:
            files = adapter.event_files(task_dir)
            if files:
                acc, _ = parse_one_file(files[-1], adapter)
                sid = acc.get("session")
        if not sid:
            raise SystemExit(f"--resume auto: no session recorded in {task_dir}")
    else:
        sid = str(resume)
    overridden = False
    if adapter.key == "cmd":
        found = find_cmd_cwd(sid, task_dir, runs_file)
        if found:
            cwd = Path(found)
            overridden = True
    return sid, cwd, overridden


def command_run(args):
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    adapter = ADAPTERS[args.agent]
    task_dir = Path(args.task_dir).expanduser().resolve()
    task_dir.mkdir(parents=True, exist_ok=True)
    cwd = Path(args.cwd).expanduser().resolve()
    if not cwd.is_dir():
        raise SystemExit(f"cwd does not exist: {cwd}")
    prompt_file = Path(args.prompt_file).expanduser().resolve()
    try:
        prompt = prompt_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"cannot read prompt file: {exc}")

    model = args.model or adapter.default_model
    effort = args.effort or adapter.default_effort
    if adapter.key == "agy" and effort is not None:
        raise SystemExit("agy adapter does not support --effort; choose a model with the required effort")
    alias = alias_for(task_dir)
    resume_session, cwd, cwd_overridden = resolve_resume(adapter, task_dir, args.resume, cwd, RUNS_FILE)

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    started = now_iso()
    start_record = {
        "run_id": run_id,
        "name": args.name,
        "alias": alias,
        "agent": adapter.key,
        "model": model,
        "effort": effort,
        "task_dir": str(task_dir),
        "cwd": str(cwd),
        "prompt_file": str(prompt_file),
        "started_at": started,
        "resume_of": resume_session,
    }
    append_json(RUNS_FILE, start_record)

    print(f"[dispatch] {run_id}  {alias}  {adapter.key}  {args.name}", flush=True)
    print(f"[dispatch] task-dir={task_dir}", flush=True)
    print(f"[dispatch] cwd={cwd}" + ("  (from recorded session cwd)" if cwd_overridden else ""), flush=True)
    if resume_session:
        print(f"[dispatch] resume={resume_session}", flush=True)

    events_files = []
    retries = 0
    rc = None
    last_acc = adapter.new_acc()
    status = None
    session = resume_session
    current_prompt = prompt

    def finish(final_status):
        end_record = {
            "run_id": run_id,
            "ended_at": now_iso(),
            "exit": rc,
            "status": final_status,
            "session": session,
            "retries": retries,
            "usage": {
                "input": int(last_acc_usage.get("input", 0)),
                "cached": int(last_acc_usage.get("cached", 0)),
                "output": int(last_acc_usage.get("output", 0)),
                "reasoning": int(last_acc_usage.get("reasoning", 0)),
            },
            "events_files": events_files,
        }
        append_json(RUNS_FILE, end_record)
        print(
            f"[dispatch] done status={final_status} exit={rc} session={session or '—'} "
            f"retries={retries} tokens={fmt_tokens(last_acc_usage.get('total', 0))}",
            flush=True,
        )
        if events_files:
            print(f"[dispatch] events={events_files[-1]}", flush=True)

    try:
        while True:
            n = adapter.event_index(task_dir)
            ev_path = adapter.event_path(task_dir, n)
            out_path = adapter.result_path(task_dir, n)
            err_path = adapter.stderr_path(task_dir, n)
            events_files.append(str(ev_path))
            cmd = adapter.build_command(
                prompt=current_prompt,
                model=model,
                effort=effort,
                resume=resume_session,
                event_path=ev_path,
                result_path=out_path,
            )
            print(f"[dispatch] exec -> {shlex.join(cmd[:6])}{' …' if len(cmd) > 6 else ''}", flush=True)
            rc = execute(cmd, cwd, ev_path, err_path, adapter.merge_stderr)
            try:
                adapter.exit_path(task_dir).write_text(str(rc), encoding="utf-8")
            except OSError:
                pass
            last_acc, _ = parse_one_file(ev_path, adapter)
            session = last_acc.get("session") or session
            if session:
                try:
                    adapter.session_path(task_dir).write_text(session, encoding="utf-8")
                except OSError:
                    pass
            write_result(adapter, task_dir, out_path, last_acc)

            decision = adapter.auto_resume(
                last_acc, rc,
                {
                    "attempt": retries,
                    "delay": int(os.environ.get(
                        f"DISPATCH_{adapter.key.upper()}_RETRY_SLEEP", str(adapter.retry_sleep))),
                    "max_attempts": adapter.max_retries,
                },
            )
            if decision:
                retries += 1
                resume_session = decision["session"]
                current_prompt = decision["prompt"]
                if decision.get("cwd"):
                    cwd = Path(decision["cwd"])
                print(
                    f"[dispatch] auto-resume ({decision['reason']}) retry {retries} "
                    f"session={resume_session} sleep={decision['delay']}s",
                    flush=True,
                )
                if decision["delay"] > 0:
                    time.sleep(decision["delay"])
                continue
            break
        status = adapter.classify(last_acc, rc)
    except Terminated:
        status = "killed"
        if rc is None:
            rc = -15
        print("[dispatch] terminated by signal", flush=True)
    except Exception as exc:  # keep the ledger honest even on a crash
        status = "failed"
        print(f"[dispatch] internal error: {exc}", flush=True)
    finally:
        try:
            combined = combine_files([Path(p) for p in events_files], adapter, mode="full", cache=None)
            last_acc_usage = combined["usage"]
            session = combined.get("session") or session
        except Exception:
            last_acc_usage = adapter.usage(last_acc)
        if status is None:
            try:
                status = adapter.classify(last_acc, rc)
            except Exception:
                status = "failed"
        finish(status)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def collect_rows(runs_file=None, root=None):
    prices = load_prices()
    runs = read_runs(runs_file or RUNS_FILE)
    with _CACHE_LOCK:
        rows = [row_for_run(r, prices, cache=_CACHE) for r in runs]
        exclude = {(norm_path(r.get("task_dir") or ""), r.get("agent")) for r in runs if r.get("task_dir")}
        legacy = scan_legacy(root, exclude_pairs=exclude, cache=_CACHE, prices=prices)
    return rows, legacy, prices


def command_status(args):
    rows, legacy, prices = collect_rows()
    if getattr(args, "json", False):
        print(json.dumps({"runs": rows, "legacy": legacy}, ensure_ascii=False, indent=2))
        return

    all_rows = rows + legacy
    all_rows.sort(key=lambda r: (
        0 if r["status"] in ("running", "starting") else 1,
        -(r.get("last_activity_ago") or 0),
    ))

    headers = [
        ("名字", 26), ("化名", 13), ("AGENT", 6), ("模型/强度", 28),
        ("状态", 10), ("已跑/耗时", 11), ("最近活动", 10), ("TOKEN", 9), ("费用", 8),
    ]
    line = "  ".join(pad(h, w) for h, w in headers)
    print(line)
    print("  ".join("-" * w for _, w in headers))
    for r in all_rows:
        model = r.get("model") or "—"
        if r.get("effort"):
            model = f"{model} / {r['effort']}"
        cost = "—" if r.get("cost_usd") is None else f"${r['cost_usd']:.3f}"
        name = trunc(("⚑ " if r.get("legacy") else "") + str(r.get("name") or "—"), 26)
        cells = [
            pad(name, 26),
            pad(trunc(r.get("alias") or "—", 13), 13),
            pad(r.get("agent") or "—", 6),
            pad(trunc(model, 28), 28),
            pad(r.get("status") or "—", 10),
            pad(fmt_duration(r.get("elapsed_seconds")), 11),
            pad(fmt_ago(r.get("last_activity_ago")), 10),
            pad(fmt_tokens(r.get("usage", {}).get("total")), 9),
            pad(cost, 8),
        ]
        print("  ".join(cells))

    running = sum(1 for r in all_rows if r["status"] in ("running", "starting"))
    total_tokens = sum(int(r.get("usage", {}).get("total") or 0) for r in all_rows)
    total_elapsed = sum(float(r.get("elapsed_seconds") or 0) for r in all_rows)
    costs = [r["cost_usd"] for r in all_rows if r.get("cost_usd") is not None]
    total_cost = f"${sum(costs):.3f}" if costs else "—"
    print()
    print(
        f"运行中 {running} · runs {len(rows)} · legacy {len(legacy)} · "
        f"总 token {fmt_tokens(total_tokens)} · 总耗时 {fmt_duration(total_elapsed)} · 总费用 {total_cost}"
    )
    if not prices:
        print("（prices.json 为空或缺失：费用显示为 —）")


# ---------------------------------------------------------------------------
# board
# ---------------------------------------------------------------------------

HTML_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dispatch 看板</title>
<style>
  :root {
    --bg: #0b0e14; --panel: #121722; --panel2: #171e2c; --line: #232c3d;
    --text: #e6edf7; --muted: #8b98ad; --dim: #5d6b82;
    --codex: #7c9cff; --agy: #4fd1a5; --cmd: #f2b35c; --other: #b58cff;
    --ok: #4fd1a5; --fail: #ff6b7a; --warn: #f2b35c; --run: #7c9cff;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: var(--bg); color: var(--text); }
  body {
    font-family: ui-sans-serif, -apple-system, "SF Pro Text", "PingFang SC", "Hiragino Sans GB", sans-serif;
    font-size: 14px; line-height: 1.45;
  }
  .wrap { max-width: 1480px; margin: 0 auto; padding: 20px 22px 60px; }
  header { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; margin-bottom: 18px; }
  header h1 { font-size: 20px; letter-spacing: .16em; margin: 0; font-weight: 700; }
  header h1 span { color: var(--codex); }
  .sub { color: var(--muted); font-size: 12px; }
  .live { display: inline-flex; align-items: center; gap: 7px; color: var(--muted); font-size: 12px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ok); box-shadow: 0 0 0 0 rgba(79,209,165,.6); animation: pulse 2s infinite; }
  @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(79,209,165,.5); } 70% { box-shadow: 0 0 0 8px rgba(79,209,165,0); } 100% { box-shadow: 0 0 0 0 rgba(79,209,165,0); } }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-bottom: 16px; }
  .stat { background: linear-gradient(180deg, var(--panel2), var(--panel)); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; }
  .stat .k { color: var(--muted); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
  .stat .v { font-size: 26px; font-weight: 700; margin-top: 4px; font-variant-numeric: tabular-nums; }
  .stat .v small { font-size: 12px; color: var(--muted); font-weight: 400; margin-left: 6px; }
  .charts { display: grid; grid-template-columns: minmax(300px, 1fr) minmax(360px, 1.5fr); gap: 12px; margin-bottom: 16px; }
  .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 16px; }
  .panel h2 { margin: 0 0 12px; font-size: 12px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); font-weight: 600; }
  .donut-wrap { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
  .donut-wrap svg { flex: 0 0 190px; }
  .legend { display: flex; flex-direction: column; gap: 9px; min-width: 140px; }
  .legend .item { display: flex; align-items: center; gap: 8px; font-size: 12px; }
  .swatch { width: 9px; height: 9px; border-radius: 2px; }
  .legend .pct { color: var(--muted); margin-left: auto; font-variant-numeric: tabular-nums; }
  .bars { display: flex; flex-direction: column; gap: 8px; }
  .bar-row { display: grid; grid-template-columns: minmax(110px, 190px) 1fr 64px; align-items: center; gap: 10px; font-size: 12px; }
  .bar-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }
  .bar-label .fam { color: var(--dim); font-size: 10px; margin-left: 5px; text-transform: uppercase; }
  .bar-track { height: 10px; background: #0a0d13; border-radius: 6px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 6px; min-width: 2px; }
  .bar-val { text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; }
  .table-wrap { padding: 0; overflow: hidden; }
  .panel-head { display: flex; align-items: baseline; justify-content: space-between; padding: 16px 16px 10px; }
  .panel-head h2 { margin: 0; }
  .scroll { overflow: auto; max-height: 62vh; }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  th { position: sticky; top: 0; z-index: 2; background: #0f141d; color: var(--muted); text-align: left; font-weight: 600; font-size: 10.5px; letter-spacing: .07em; text-transform: uppercase; padding: 9px 10px; border-bottom: 1px solid var(--line); white-space: nowrap; }
  td { padding: 9px 10px; border-bottom: 1px solid #1a2231; vertical-align: middle; white-space: nowrap; }
  tr:hover td { background: #141b28; }
  .name { font-weight: 600; }
  .alias { color: var(--muted); }
  .agent { font-weight: 700; letter-spacing: .04em; font-size: 11px; }
  .a-codex { color: var(--codex); } .a-agy { color: var(--agy); } .a-cmd { color: var(--cmd); } .a-other { color: var(--other); }
  .status { display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: 999px; font-size: 10.5px; font-weight: 700; letter-spacing: .04em; border: 1px solid transparent; }
  .st-ok { color: var(--ok); background: rgba(79,209,165,.1); border-color: rgba(79,209,165,.25); }
  .st-failed, .st-killed { color: var(--fail); background: rgba(255,107,122,.1); border-color: rgba(255,107,122,.25); }
  .st-capacity, .st-max_turns, .st-no_result { color: var(--warn); background: rgba(242,179,92,.1); border-color: rgba(242,179,92,.25); }
  .st-running, .st-starting { color: var(--run); background: rgba(124,156,255,.12); border-color: rgba(124,156,255,.3); }
  .st-running::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--run); animation: pulse 1.4s infinite; }
  .mono { font-variant-numeric: tabular-nums; }
  .muted { color: var(--muted); }
  .badge { display: inline-block; margin-left: 6px; padding: 1px 5px; border-radius: 4px; background: #1b2434; color: var(--dim); font-size: 9.5px; letter-spacing: .06em; }
  .tokbar { display: inline-flex; height: 5px; width: 74px; border-radius: 3px; overflow: hidden; background: #0a0d13; vertical-align: middle; margin-left: 7px; }
  .tokbar i { display: block; height: 100%; }
  .err { color: var(--fail); padding: 20px; }
  @media (max-width: 900px) { .charts { grid-template-columns: 1fr; } .scroll { max-height: none; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>DISPATCH<span>_</span></h1>
    <div class="sub" id="root"></div>
    <div class="live"><span class="dot"></span><span id="stamp">连接中…</span></div>
  </header>

  <section class="stats" id="stats"></section>

  <section class="charts">
    <div class="panel">
      <h2>Agent 家族 token 占比</h2>
      <div id="donut" class="donut-wrap"></div>
    </div>
    <div class="panel">
      <h2>各 run token</h2>
      <div id="bars" class="bars"></div>
    </div>
  </section>

  <section class="panel table-wrap">
    <div class="panel-head">
      <h2>Runs</h2>
      <span class="sub" id="count"></span>
    </div>
    <div class="scroll">
      <table>
        <thead><tr>
          <th>名字</th><th>化名</th><th>Agent</th><th>模型 / 强度</th><th>状态</th>
          <th>已跑 / 耗时</th><th>最近活动</th><th>Token</th><th>费用</th>
        </tr></thead>
        <tbody id="rows"></tbody>
      </table>
    </div>
  </section>
</div>

<script>
const COLORS = {codex:'#7c9cff', agy:'#4fd1a5', cmd:'#f2b35c', other:'#b58cff'};
const STATUS_LABEL = {ok:'ok', failed:'failed', capacity:'capacity', max_turns:'max turns', no_result:'no result', killed:'killed', running:'running', starting:'starting'};

function esc(v) {
  return String(v == null ? '' : v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function color(a) { return COLORS[a] || COLORS.other; }
function fmtTokens(n) {
  n = Number(n || 0);
  if (n >= 1e9) return (n/1e9).toFixed(2) + 'B';
  if (n >= 1e6) return (n/1e6).toFixed(2) + 'M';
  if (n >= 1e3) return (n/1e3).toFixed(1) + 'k';
  return String(Math.round(n));
}
function fmtDur(s) {
  if (s == null) return '—';
  s = Math.max(0, Math.round(s));
  if (s < 60) return s + 's';
  if (s < 3600) return Math.floor(s/60) + 'm' + String(s%60).padStart(2,'0') + 's';
  if (s < 86400) return Math.floor(s/3600) + 'h' + String(Math.floor((s%3600)/60)).padStart(2,'0') + 'm';
  return Math.floor(s/86400) + 'd' + Math.floor((s%86400)/3600) + 'h';
}
function fmtAgo(s) {
  if (s == null) return '—';
  s = Math.max(0, Math.round(s));
  if (s < 60) return s + 's 前';
  if (s < 3600) return Math.floor(s/60) + 'm 前';
  if (s < 86400) return Math.floor(s/3600) + 'h 前';
  return Math.floor(s/86400) + 'd 前';
}
function fmtCost(v) { return (v == null) ? '—' : '$' + Number(v).toFixed(3); }
function statusClass(s) { return 'st-' + String(s || 'other').replace(/[^a-z_]/g, ''); }

function renderStats(d) {
  const s = d.summary;
  const cards = [
    ['运行中', s.running, s.run_count + ' runs · ' + s.legacy_count + ' legacy'],
    ['总 token', fmtTokens(s.total_tokens), 'all agents'],
    ['总耗时', fmtDur(s.total_elapsed_seconds), 'sum of run durations'],
    ['总费用', fmtCost(s.total_cost_usd), s.priced_rows ? s.priced_rows + ' priced rows' : 'prices.json 为空'],
  ];
  document.getElementById('stats').innerHTML = cards.map(([k,v,sub]) =>
    `<div class="stat"><div class="k">${esc(k)}</div><div class="v">${esc(v)}<small>${esc(sub)}</small></div></div>`
  ).join('');
  document.getElementById('root').textContent = d.root;
  document.getElementById('count').textContent = (d.runs.length + d.legacy.length) + ' 行 · ' + d.generated_at;
}

function renderDonut(d) {
  const entries = Object.entries(d.summary.by_agent || {}).filter(([k,v]) => v.tokens > 0);
  const total = entries.reduce((a,[,v]) => a + v.tokens, 0);
  const el = document.getElementById('donut');
  if (!total) { el.innerHTML = '<div class="muted">暂无 token 数据</div>'; return; }
  const R = 70, C = 2 * Math.PI * R;
  let offset = 0;
  const segs = entries.map(([k,v]) => {
    const len = v.tokens / total * C;
    const seg = `<circle r="${R}" cx="100" cy="100" fill="none" stroke="${color(k)}" stroke-width="30" stroke-dasharray="${len} ${C-len}" stroke-dashoffset="${-offset}" transform="rotate(-90 100 100)"></circle>`;
    offset += len;
    return seg;
  }).join('');
  const legend = entries.sort((a,b)=>b[1].tokens-a[1].tokens).map(([k,v]) => {
    const pct = (v.tokens / total * 100).toFixed(1);
    return `<div class="item"><span class="swatch" style="background:${color(k)}"></span><span class="a-${esc(k)}">${esc(k)}</span><span class="pct">${pct}%</span></div>`;
  }).join('');
  el.innerHTML = `
    <svg width="190" height="190" viewBox="0 0 200 200">
      <circle r="${R}" cx="100" cy="100" fill="none" stroke="#0a0d13" stroke-width="30"></circle>
      ${segs}
      <text x="100" y="96" text-anchor="middle" fill="#e6edf7" font-size="19" font-weight="700">${fmtTokens(total)}</text>
      <text x="100" y="115" text-anchor="middle" fill="#8b98ad" font-size="10">TOTAL TOKENS</text>
    </svg>
    <div class="legend">${legend}</div>`;
}

function renderBars(rows) {
  const top = [...rows].sort((a,b) => (b.usage.total||0) - (a.usage.total||0)).slice(0, 12);
  const max = Math.max(1, ...top.map(r => r.usage.total || 0));
  const el = document.getElementById('bars');
  if (!top.length) { el.innerHTML = '<div class="muted">暂无 run</div>'; return; }
  el.innerHTML = top.map(r => {
    const pct = Math.max(1, (r.usage.total || 0) / max * 100);
    return `<div class="bar-row">
      <div class="bar-label" title="${esc(r.name)}">${esc(r.name)}<span class="fam a-${esc(r.agent)}">${esc(r.agent)}</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${color(r.agent)}"></div></div>
      <div class="bar-val">${fmtTokens(r.usage.total)}</div>
    </div>`;
  }).join('');
}

function tokenMini(u) {
  const total = u.total || 1;
  const a = (u.input||0)/total*100, b = (u.cached||0)/total*100, c = (u.output||0)/total*100;
  return `<span class="tokbar"><i style="width:${a}%;background:#7c9cff"></i><i style="width:${b}%;background:#3d4d70"></i><i style="width:${c}%;background:#4fd1a5"></i></span>`;
}

function renderTable(d) {
  const rows = [...d.runs, ...d.legacy];
  rows.sort((a,b) => {
    const ar = (a.status === 'running' || a.status === 'starting') ? 0 : 1;
    const br = (b.status === 'running' || b.status === 'starting') ? 0 : 1;
    if (ar !== br) return ar - br;
    return (a.last_activity_ago || 1e12) - (b.last_activity_ago || 1e12);
  });
  document.getElementById('rows').innerHTML = rows.map(r => {
    const model = r.model ? esc(r.model) + (r.effort ? ' / ' + esc(r.effort) : '') : '—';
    const legacy = r.legacy ? '<span class="badge">LEGACY</span>' : '';
    const u = r.usage || {};
    return `<tr>
      <td><span class="name">${esc(r.name)}</span>${legacy}</td>
      <td class="alias">${esc(r.alias)}</td>
      <td><span class="agent a-${esc(r.agent)}">${esc(r.agent)}</span></td>
      <td class="muted">${model}</td>
      <td><span class="status ${statusClass(r.status)}">${esc(STATUS_LABEL[r.status] || r.status)}</span></td>
      <td class="mono">${fmtDur(r.elapsed_seconds)}</td>
      <td class="muted">${fmtAgo(r.last_activity_ago)}</td>
      <td class="mono" title="input ${u.input||0} · cached ${u.cached||0} · output ${u.output||0} · reasoning ${u.reasoning||0}">${fmtTokens(u.total)}${tokenMini(u)}</td>
      <td class="mono ${r.cost_usd == null ? 'muted' : ''}">${fmtCost(r.cost_usd)}</td>
    </tr>`;
  }).join('');
}

async function tick() {
  try {
    const res = await fetch('/data.json', {cache: 'no-store'});
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const d = await res.json();
    renderStats(d);
    renderDonut(d);
    renderBars([...d.runs, ...d.legacy]);
    renderTable(d);
    const t = new Date();
    document.getElementById('stamp').textContent = '更新于 ' + t.toLocaleTimeString('zh-CN', {hour12:false});
  } catch (e) {
    document.getElementById('stamp').textContent = '连接失败：' + e.message;
  }
}
tick();
setInterval(tick, 10000);
</script>
</body>
</html>
"""


class BoardHandler(BaseHTTPRequestHandler):
    server_version = "dispatch-board/1.0"

    def _send(self, code, body, content_type):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, HTML_PAGE, "text/html; charset=utf-8")
        elif path == "/data.json":
            try:
                data = build_data()
                self._send(200, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")
            except Exception as exc:
                self._send(500, json.dumps({"error": str(exc)}, ensure_ascii=False), "application/json; charset=utf-8")
        elif path == "/healthz":
            self._send(200, "ok", "text/plain; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    def log_message(self, fmt, *args):
        pass


def command_board(args):
    host = args.host
    port = args.port
    try:
        httpd = ThreadingHTTPServer((host, port), BoardHandler)
    except OSError as exc:
        raise SystemExit(f"cannot bind {host}:{port}: {exc}")
    httpd.daemon_threads = True
    url = f"http://{host}:{port}/"
    print(f"[dispatch] board on {url}  (auto-refresh {REFRESH_SECONDS}s)")
    print(f"[dispatch] runs={RUNS_FILE}")
    print(f"[dispatch] legacy root={DEFAULT_ROOT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[dispatch] board stopped")
    finally:
        httpd.server_close()


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="dispatch.py",
        description="统一的 coding-agent 派活工具 + 实时看板",
    )
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="派一个任务（前台运行）")
    r.add_argument("--name", required=True, help="这个 agent 在干什么，例如「Dorico-小谱号修复」")
    r.add_argument("--agent", required=True, choices=sorted(ADAPTERS.keys()))
    r.add_argument("--task-dir", required=True, help="派活目录（事件/结果/会话文件写这里）")
    r.add_argument("--cwd", required=True, help="agent 的工作目录")
    r.add_argument("--prompt-file", required=True, help="提示词文件")
    r.add_argument("--model", default=None)
    r.add_argument("--effort", default=None, help="codex/cmd 推理强度；可用值以当前 CLI 和模型为准")
    r.add_argument("--resume", default=None, help="会话号，或 auto（读 task-dir 里的会话号文件）")
    r.set_defaults(func=command_run)

    s = sub.add_parser("status", help="终端里打一张巡检表")
    s.add_argument("--json", action="store_true", help="输出 JSON")
    s.set_defaults(func=command_status)

    b = sub.add_parser("board", help="启动本机看板 HTTP 服务")
    b.add_argument("--port", type=int, default=8765)
    b.add_argument("--host", default="127.0.0.1")
    b.set_defaults(func=command_board)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
