#!/usr/bin/env python3
"""Standard-library dispatcher, terminal status and read-only orchestration board.

Run `dispatch.py --help` for commands. Task output and the runs.jsonl ledger
remain separate from the bounded, atomically replaced board state.
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
import time
import threading
import unicodedata
import uuid
from pathlib import Path

import board

APP_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = Path(os.environ.get("DISPATCH_ROOT", str(board.state_root() / "dispatch")))
RUNS_FILE = Path(os.environ.get("DISPATCH_RUNS", str(DEFAULT_ROOT / "runs.jsonl")))
PRICES_FILE = Path(os.environ.get("DISPATCH_PRICES", str(APP_DIR / "prices.json")))
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
            "-m", model,
            "-c", f"model_reasoning_effort={effort}",
            "-c", "service_tier=default",
            "-o", str(result_path),
            "--json",
            prompt,
        ])
        return cmd


class AgyAdapter(Adapter):
    key = "agy"
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
            "--model", model,
            "--dangerously-skip-permissions",
            "--output-format", "stream-json",
            "--print-timeout", "0",
        ]
        if resume:
            cmd.extend(["--conversation", str(resume)])
        return cmd


class CmdAdapter(Adapter):
    key = "cmd"
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
            "-m", model,
            "--yolo", "--trust", "--skip-onboarding", "--no-auto-update",
            "--output-format", "json", "--max-turns", "1500",
        ]
        if effort != "none":
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


def board_write(action, **kwargs):
    """Board failures must never turn an otherwise valid dispatch into a failure."""
    try:
        action(**kwargs)
        return True
    except Terminated:
        raise  # preserve user termination, rather than treating it as a board error
    except Exception as exc:
        print(f"[dispatch] board {getattr(action, '__name__', 'write')} warning: {exc}", file=sys.stderr, flush=True)
        return False


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

    model = args.model
    effort = args.effort
    if adapter.key == "agy" and effort != "none":
        raise ValueError("agy has no effort control; explicitly use --effort none")
    alias = alias_for(task_dir)
    resume_session, cwd, cwd_overridden = resolve_resume(adapter, task_dir, args.resume, cwd, RUNS_FILE)

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    started = now_iso()
    start_record = {
        "run_id": run_id,
        "name": args.name,
        "doing": args.doing,
        "pid": os.getpid(),
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
    registered = board_write(board.start, name=args.name, doing=args.doing, tool=adapter.key, model=model,
                effort=effort, cwd=cwd, task_dir=task_dir, pid=os.getpid(), lane_id=run_id)
    append_json(RUNS_FILE, start_record)
    stopped = threading.Event()

    def heartbeat():
        while not stopped.wait(board.HEARTBEAT_SECONDS):
            if not board_write(board.update, lane_id=run_id):
                return

    pulse = None
    if registered:
        pulse = threading.Thread(target=heartbeat, daemon=True)
        pulse.start()

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
        stopped.set()
        if pulse is not None:
            pulse.join()
        board_status = "ok" if final_status == "ok" else "aborted" if final_status == "killed" else "failed"
        if registered:
            board_write(board.update, lane_id=run_id, status=board_status)
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
    return 0 if status == "ok" else (rc if rc and rc > 0 else 1)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def collect_rows(runs_file=None, root=None):
    prices = load_prices()
    runs = read_runs(runs_file or RUNS_FILE)
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
# cli
# ---------------------------------------------------------------------------

def nonblank(value):
    value = value.strip()
    if not value:
        raise argparse.ArgumentTypeError("must not be blank")
    return value


def command_start(args):
    print(board.start(name=args.name, doing=args.doing, tool=args.tool, model=args.model,
                      effort=args.effort, cwd=args.cwd, task_dir=args.task_dir, pid=args.pid))


def command_update(args):
    board.update(args.lane, doing=args.doing)


def command_end(args):
    board.update(args.lane, status=args.status)


def build_parser():
    p = argparse.ArgumentParser(
        prog="dispatch.py",
        description="coding-agent 派活、巡检与编排看板（仅 Python 标准库）",
    )
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="派一个任务（前台运行）")
    r.add_argument("--name", required=True, type=nonblank, help="简短车道名")
    r.add_argument("--doing", required=True, type=nonblank, help="当前在做什么")
    r.add_argument("--agent", required=True, choices=sorted(ADAPTERS.keys()))
    r.add_argument("--task-dir", required=True, help="派活目录（事件/结果/会话文件写这里）")
    r.add_argument("--cwd", required=True, help="agent 的工作目录")
    r.add_argument("--prompt-file", required=True, help="提示词文件")
    r.add_argument("--model", required=True, type=nonblank)
    r.add_argument("--effort", required=True, type=nonblank, help="显式选择推理强度；不可调工具必须填 none（agy 仅接受 none）")
    r.add_argument("--resume", default=None, help="会话号，或 auto（读 task-dir 里的会话号文件）")
    r.set_defaults(func=command_run)

    s = sub.add_parser("status", help="终端里打一张巡检表")
    s.add_argument("--json", action="store_true", help="输出 JSON")
    s.set_defaults(func=command_status)

    a = sub.add_parser("start", help="登记外部车道，输出车道 ID；PID 必须为本机存活的长期进程")
    for key in ("name", "doing", "tool", "model", "effort"):
        a.add_argument("--" + key, required=True, type=nonblank)
    a.add_argument("--cwd", type=nonblank, default=None, help="默认当前目录")
    a.add_argument("--task-dir", type=nonblank, default=None, help="可选任务目录")
    a.add_argument("--pid", type=int, default=None, help="默认调用进程 PID；Claude Code shell 工具显式传 $PPID")
    a.set_defaults(func=command_start)

    u = sub.add_parser("update", help="更新车道当前在做什么")
    u.add_argument("--lane", required=True, type=nonblank)
    u.add_argument("--doing", required=True, type=nonblank)
    u.set_defaults(func=command_update)

    e = sub.add_parser("end", help="标记车道结束（只记状态，不终止进程）")
    e.add_argument("--lane", required=True, type=nonblank)
    e.add_argument("--status", required=True, choices=("ok", "failed", "aborted"))
    e.set_defaults(func=command_end)

    b = sub.add_parser("board", help="启动只读网页；默认仅绑定自动发现的 Tailscale IPv4")
    b.add_argument("--host", help="显式绑定地址；本机验证可用 127.0.0.1")
    b.add_argument("--port", type=int, default=board.DEFAULT_PORT)
    b.add_argument("--allow-host", action="append", default=[], metavar="NAME",
                   help="额外允许的访问主机名（不含端口）；可重复")
    b.set_defaults(func=lambda args: board.serve(args.host, args.port, args.allow_host))
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"dispatch: {exc}") from exc


if __name__ == "__main__":
    sys.exit(main())
