"""Small, local dispatch board. Standard library only; no agent CLI imports."""
from __future__ import annotations

import base64
from contextlib import contextmanager
import datetime as dt
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

HISTORY_LIMIT = 20
HEARTBEAT_SECONDS = 5
DEFAULT_PORT = 18743


def state_root():
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))).expanduser()


def state_path():
    return Path(os.environ.get("DISPATCH_BOARD_STATE", str(state_root() / "dispatch/board.json"))).expanduser()


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def epoch(value):
    return dt.datetime.fromisoformat(value).timestamp()


def alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        # Windows os.kill(pid, 0) can terminate the target; query its handle instead.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # access denied is not proof of death
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextmanager
def locked(path):
    """Lock a stable sidecar, never the inode replaced by atomic writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".lock", "a+b") as lock:
        if os.name == "nt":
            import msvcrt
            if os.fstat(lock.fileno()).st_size == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            while True:
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (13, 36):
                        raise
                    time.sleep(0.05)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def load(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": 1, "lanes": []}
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("lanes"), list):
        raise ValueError("unsupported board state format")
    return data


def reconcile(lanes):
    for lane in lanes:
        if lane["status"] == "running" and not alive(lane["pid"]):
            lane.update(status="aborted", ended_at=lane["updated_at"])
    return lanes


def partition(lanes):
    running = sorted((r for r in lanes if r["status"] == "running"), key=lambda r: r["started_at"])
    ended = [r for _, r in sorted(
        ((i, r) for i, r in enumerate(lanes) if r["status"] != "running"),
        key=lambda pair: (pair[1]["ended_at"], pair[0]), reverse=True)[:HISTORY_LIMIT]]
    return running, ended


def mutate(change):
    path = state_path()
    with locked(path):
        data = load(path)
        reconcile(data["lanes"])
        result = change(data["lanes"])
        running, ended = partition(data["lanes"])
        keep = {r["id"] for r in running + ended}
        data["lanes"] = [r for r in data["lanes"] if r["id"] in keep]
        fd, temporary = tempfile.mkstemp(prefix=".board-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(data, out, ensure_ascii=False, indent=2)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return result


def start(*, name, doing, tool, model, effort, cwd=None, task_dir=None, pid=None, lane_id=None):
    if not all(str(v).strip() for v in (name, doing, tool, model, effort)):
        raise ValueError("name, doing, tool, model and effort must not be blank")
    pid = os.getppid() if pid is None else pid
    if not alive(pid):
        raise ValueError("--pid must identify a live local process")
    lane_id = lane_id or uuid.uuid4().hex
    now = stamp()
    record = dict(id=lane_id, name=name, doing=doing, tool=tool, model=model, effort=effort,
                  cwd=str(Path(cwd or Path.cwd()).expanduser().resolve()),
                  task_dir=str(Path(task_dir).expanduser().resolve()) if task_dir else None, pid=pid,
                  started_at=now, updated_at=now, ended_at=None, status="running")

    def add(lanes):
        if any(r["id"] == lane_id for r in lanes):
            raise ValueError(f"lane already exists: {lane_id}")
        lanes.append(record)
        return lane_id
    return mutate(add)


def update(lane_id, *, doing=None, status=None):
    def change(lanes):
        for lane in lanes:
            if lane["id"] != lane_id:
                continue
            if lane["status"] != "running":
                raise ValueError(f"lane already ended: {lane_id}")
            now = stamp()
            if doing is not None:
                if not doing.strip():
                    raise ValueError("doing must not be blank")
                lane["doing"] = doing
            lane["updated_at"] = now
            if status is not None:
                if status not in ("ok", "failed", "aborted"):
                    raise ValueError("invalid end status")
                lane.update(status=status, ended_at=now)
            return
        raise ValueError(f"unknown lane: {lane_id}")
    mutate(change)


def snapshot():
    # Atomic replacement makes reads safe without a write lock or read-side writes.
    running, ended = partition(reconcile(load(state_path())["lanes"]))
    now = time.time()
    for lane in running + ended:
        end = epoch(lane["ended_at"]) if lane["ended_at"] else now
        lane["elapsed_seconds"] = max(0, end - epoch(lane["started_at"]))
        lane["updated_ago_seconds"] = max(0, now - epoch(lane["updated_at"]))
    return running, ended


def template():
    return Path(__file__).with_name("board.html").read_text(encoding="utf-8")


def render():
    """Embed the snapshot as JSON the page script draws from; `<`, `>` and `&` are escaped
    so no user string can close the data block or open markup."""
    running, ended = snapshot()
    data = json.dumps({"now": time.time(), "history_limit": HISTORY_LIMIT,
                       "running": running, "ended": ended}, ensure_ascii=False)
    for raw, safe in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e")):
        data = data.replace(raw, safe)
    return template().replace("{{DATA}}", data)


def policy():
    """CSP allowing only the template's own inline script, by hash."""
    hashes = " ".join("'sha256-%s'" % base64.b64encode(hashlib.sha256(code.encode("utf-8")).digest()).decode()
                      for code in re.findall(r"<script>(.*?)</script>", template(), re.S))
    return (f"default-src 'none'; style-src 'unsafe-inline'; script-src {hashes}; "
            "connect-src 'self'; frame-ancestors 'none'")


class Server(ThreadingHTTPServer):
    def __init__(self, address, handler):
        super().__init__(address, handler)
        self.expected_host = f"{address[0]}:{self.server_port}".lower()


class Handler(BaseHTTPRequestHandler):
    def parse_request(self):
        if not super().parse_request():
            return False
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or hosts[0].lower() != self.server.expected_host:
            self.send_error(400, "Host does not match board address")
            return False
        return True

    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        try:
            body = render().encode("utf-8")
            csp = policy()
        except (OSError, ValueError, KeyError, TypeError):
            self.send_error(503, "Cannot read board state")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", csp)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def tailscale_host():
    try:
        output = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True,
                                timeout=5, check=True).stdout.strip().splitlines()
        host = str(ipaddress.IPv4Address(output[0]))
        if ipaddress.IPv4Address(host) not in ipaddress.IPv4Network("100.64.0.0/10"):
            raise ValueError("not a Tailscale IPv4 address")
        return host
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as exc:
        raise ValueError("cannot get Tailscale IPv4; specify --host (e.g. --host 127.0.0.1)") from exc


def serve(host, port):
    host = host or tailscale_host()
    with Server((host, port), Handler) as server:
        print(f"Dispatch board: http://{host}:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
