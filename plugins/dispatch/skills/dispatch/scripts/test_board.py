#!/usr/bin/env python3
"""Board contract tests. All state is isolated; no model CLI is launched."""
import base64
import contextlib
import hashlib
import io
import http.client
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen, Request

import board
import dispatch


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "board.json"
        env = patch.dict(os.environ, {"DISPATCH_BOARD_STATE": str(self.path)})
        env.start()
        self.addCleanup(env.stop)

    def start(self, **kwargs):
        values = dict(name="审查", doing="检查边界", tool="claude-agent", model="chosen-model",
                      effort="high", cwd=self.root, task_dir=self.root, pid=os.getpid())
        values.update(kwargs)
        return board.start(**values)

    @staticmethod
    def payload(page):
        match = re.search(r'<script type="application/json" id="board-data">(.*?)</script>', page, re.S)
        return json.loads(match[1])

    def test_required_fields_even_on_resume(self):
        parser = dispatch.build_parser()
        run = ["run", "--name", "lane", "--agent", "codex", "--model", "m",
               "--effort", "high", "--doing", "review", "--task-dir", str(self.root),
               "--cwd", str(self.root), "--prompt-file", "prompt.txt"]
        manual = ["start", "--name", "lane", "--tool", "other-cli", "--model", "m",
                  "--effort", "none", "--doing", "review", "--task-dir", str(self.root),
                  "--cwd", str(self.root), "--pid", str(os.getpid())]
        for command, fields in ((run, ("--agent", "--model", "--effort", "--doing")),
                                (run + ["--resume", "sid"], ("--model", "--effort", "--doing")),
                                (manual, ("--name", "--tool", "--model", "--effort", "--doing"))):
            for flag in fields:
                i = command.index(flag)
                with self.subTest(command=command[0], flag=flag), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as exc:
                        parser.parse_args(command[:i] + command[i + 2:])
                    self.assertEqual(exc.exception.code, 2)
            parser.parse_args(command)
        for flag in ("--name", "--tool", "--model", "--effort", "--doing"):
            invalid = list(manual)
            invalid[invalid.index(flag) + 1] = "   "
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parser.parse_args(invalid)
        self.assertFalse(self.path.exists())

    def test_start_only_requires_five_business_fields(self):
        args = dispatch.build_parser().parse_args([
            "start", "--name", "lane", "--tool", "claude-agent", "--model", "chosen",
            "--effort", "high", "--doing", "review"])
        out = io.StringIO()
        with patch.object(board.os, "getppid", return_value=os.getpid()), contextlib.redirect_stdout(out):
            dispatch.command_start(args)
        record = board.snapshot()[0][0]
        self.assertEqual(record["id"], out.getvalue().strip())
        self.assertEqual(record["cwd"], str(Path.cwd()))
        self.assertIsNone(record["task_dir"])
        self.assertEqual(record["pid"], os.getpid())

    def test_issue_urls_rejected_by_all_cli_commands(self):
        base = {"run": ["--name", "lane", "--agent", "codex", "--model", "m", "--effort", "high",
                         "--doing", "review", "--cwd", ".", "--task-dir", ".", "--prompt-file", "prompt"],
                "start": ["--name", "lane", "--tool", "other", "--model", "m", "--effort", "none", "--doing", "review"],
                "update": ["--lane", "lane"]}
        for command, args in base.items():
            for value in ("javascript:alert(1)", "data:text/html,test", "ftp://example.com/a", "/relative", "//example.com/a",
                          "https:///missing", "https://", "https://example.com:bad", "https://example.com/\n", "http:\\example.com"):
                with self.subTest(command=command, value=value), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        dispatch.build_parser().parse_args([command, *args, "--issue", value])
            parsed = dispatch.build_parser().parse_args([command, *args, "--issue", "https://example.com/a", "--issue", "http://example.com/b"])
            self.assertEqual(parsed.issue, ["https://example.com/a", "http://example.com/b"])

    def test_issues_replace_clear_and_leave_existing_work_unchanged(self):
        lane = self.start(issues=["https://example.com/first"])
        parser = dispatch.build_parser()
        dispatch.command_update(parser.parse_args(["update", "--lane", lane, "--doing", "next phase"]))
        self.assertEqual(board.snapshot()[0][0]["issues"], ["https://example.com/first"])
        dispatch.command_update(parser.parse_args(["update", "--lane", lane, "--issue", "https://example.com/second"]))
        record = board.snapshot()[0][0]
        self.assertEqual(record["doing"], "next phase")
        self.assertEqual(record["issues"], ["https://example.com/second"])
        dispatch.command_update(parser.parse_args(["update", "--lane", lane, "--clear-issues"]))
        self.assertEqual(board.snapshot()[0][0]["issues"], [])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["update", "--lane", lane, "--clear-issues", "--issue", "https://example.com"])
        with self.assertRaises(ValueError):
            dispatch.command_update(parser.parse_args(["update", "--lane", lane]))
        with self.assertRaises(ValueError):
            self.start(issues=["javascript:alert(1)"])

    def test_legacy_state_missing_issues_stays_v1(self):
        self.start()
        data = json.loads(self.path.read_text())
        del data["lanes"][0]["issues"]
        self.path.write_text(json.dumps(data))
        before = self.path.read_bytes()
        self.assertEqual(board.load(self.path)["lanes"][0]["issues"], [])
        lane = self.payload(board.render())["running"][0]
        self.assertEqual((lane["issues"], lane["issue_links"]), ([], []))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(data["version"], 1)

    def test_issue_labels(self):
        github = "https://github.com/owner/alpha/issues/163"
        pr = "https://github.com/owner/alpha/pull/164?tab=files"
        gitlab = "https://gitlab.com/group/subgroup/beta/-/merge_requests/25"
        self.assertEqual([r["label"] for r in board.issue_links([github, pr])], ["#163", "#164"])
        self.assertEqual([r["label"] for r in board.issue_links([github, pr, gitlab])], ["alpha#163", "alpha#164", "beta#25"])
        self.assertEqual(board.issue_links(["https://gitlab.com/group/beta/-/issues/12"])[0]["label"], "#12")
        self.assertEqual(board.issue_links(["https://tracker.example/ticket/163"])[0]["label"], "tracker.example")
        self.assertEqual(board.issue_links(["https://github.com.attacker.example/owner/alpha/issues/163"])[0]["label"], "github.com.attacker.example")

    def test_issue_payload_escaping_and_unsafe_edited_state(self):
        url = 'https://tracker.example/?q=\"><img/src=x/onerror=alert(1)>'
        self.start(issues=[url])
        page = board.render()
        self.assertNotIn('<img', page)
        self.assertIn('\\u003cimg', page)
        self.assertEqual(self.payload(page)["running"][0]["issue_links"], [{"url": url, "label": "tracker.example"}])
        def corrupt(lanes):
            lanes[0]["issues"] = ["javascript:alert(1)", "data:text/html,test", url]
        board.mutate(corrupt)
        self.assertEqual(board.snapshot()[0][0]["issue_links"], [{"url": url, "label": "tracker.example"}])

    def test_manual_session_cli_and_old_data(self):
        args = dispatch.build_parser().parse_args([
            "start", "--name", "lane", "--tool", "claude-agent", "--model", "m", "--effort", "high",
            "--doing", "review", "--pid", str(os.getpid()), "--session", "session-first"])
        with contextlib.redirect_stdout(io.StringIO()):
            dispatch.command_start(args)
        record = board.snapshot()[0][0]
        self.assertEqual(record["session_id"], "session-first")
        self.assertEqual(record["resume_command"], "claude attach session-first")
        dispatch.command_update(dispatch.build_parser().parse_args([
            "update", "--lane", record["id"], "--session", "session-second"]))
        self.assertEqual(board.snapshot()[0][0]["session_id"], "session-second")
        self.assertEqual(board.snapshot()[0][0]["doing"], "review")
        data = json.loads(self.path.read_text())
        del data["lanes"][0]["session_id"]
        self.path.write_text(json.dumps(data))
        record = board.snapshot()[0][0]
        self.assertEqual((record["session_id"], record["resume_command"]), ("", ""))
        self.assertEqual(json.loads(self.path.read_text())["version"], 1)

    def test_resume_mapping_and_shell_quoting(self):
        cwd = "/workspace/space and 'quote $(echo unsafe)"
        sid = "session'$(echo unsafe);next"
        expected = {"claude": ["claude", "--resume"], "claude-agent": ["claude", "--resume"],
                    "claude-code": ["claude", "--resume"], "codex": ["codex", "resume"],
                    "opencode": ["opencode", "--session"], "cmd": ["cmd", "--resume"],
                    "agy": ["agy", "--conversation"]}
        for tool, argv in expected.items():
            with self.subTest(tool=tool):
                for status in ("running", "ok", "failed", "aborted"):
                    command = board.resume_command(tool, sid, cwd, status)
                    expected = ["claude", "attach", sid] if argv[0] == "claude" and status == "running" else ["cd", cwd, "&&", *argv, sid]
                    self.assertEqual(shlex.split(command), expected)
        self.assertEqual(board.resume_command("unknown", sid, cwd), sid)
        self.assertEqual(board.resume_command("codex", "", cwd), "")
        self.start(session_id='</script><img/src=x/onerror=alert(1)>')
        page = board.render()
        self.assertNotIn('</script><img', page)
        record = self.payload(page)["running"][0]
        self.assertIn("</script><img", record["session_id"])

    def test_ended_claude_lane_copies_resume_with_cwd(self):
        lane = self.start(session_id="session-id")
        self.assertEqual(board.snapshot()[0][0]["resume_command"], "claude attach session-id")
        board.update(lane, status="ok")
        record = self.payload(board.render())["ended"][0]
        self.assertEqual(record["resume_command"], f"cd {shlex.quote(str(self.root.resolve()))} && claude --resume session-id")

    def test_run_live_session_discovery_and_resume(self):
        prompt = self.root / "prompt.txt"
        prompt.write_text("test")
        from test_dispatch import CODEX_OK, AGY_OK, CMD_OK
        for agent, events in (("codex", CODEX_OK), ("agy", AGY_OK), ("cmd", CMD_OK)):
            adapter = dispatch.ADAPTERS[agent]
            task = self.root / agent
            argv = ["run", "--name", "lane", "--doing", "review", "--agent", agent,
                    "--model", "m", "--effort", "none" if agent == "agy" else "high",
                    "--cwd", str(self.root), "--task-dir", str(task), "--prompt-file", str(prompt)]
            for mode in ("events", "resume", "auto", "file", "missing"):
                if mode == "auto":
                    task.mkdir(exist_ok=True)
                    adapter.session_path(task).write_text("resume-id")
                args = dispatch.build_parser().parse_args(argv + (
                    ["--resume", "auto" if mode == "auto" else "resume-id"] if mode in ("resume", "auto") else []))
                observed = []
                expected = (json.loads(events[0]).get("thread_id") or json.loads(events[0]).get("conversation_id")
                            or json.loads(events[0]).get("event", {}).get("sessionId")) if mode == "events" else {
                                "resume": "resume-id", "auto": "resume-id", "file": "file-id", "missing": ""}[mode]
                def fake_execute(cmd, cwd, event_path, stderr_path, merge_stderr):
                    initial = board.snapshot()[0][0]
                    observed.append(initial["session_id"])
                    event_path.write_text("\n".join(events) + "\n" if mode == "events" else "")
                    if mode == "file":
                        adapter.session_path(task).write_text("file-id")
                        os.utime(adapter.session_path(task), (time.time()+1, time.time()+1))
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        current = board.snapshot()[0][0]["session_id"]
                        if current == expected:
                            break
                        time.sleep(.01)
                    observed.append(current)
                    # End without a model CLI or adapter auto-resume/retry loop.
                    raise dispatch.Terminated()
                if task.exists():
                    old = adapter.session_path(task)
                    if old.exists():
                        os.utime(old, (1, 1))  # never inherit an unrelated old run's session
                with patch.object(dispatch, "RUNS_FILE", self.root / "runs.jsonl"), \
                        patch.object(dispatch, "execute", side_effect=fake_execute), \
                        patch.object(dispatch.signal, "signal"), patch.object(board, "HEARTBEAT_SECONDS", .01), \
                        contextlib.redirect_stdout(io.StringIO()):
                    dispatch.command_run(args)
                self.assertEqual(observed, ["resume-id" if mode in ("resume", "auto") else "", expected])
                recent = max(board.snapshot()[1], key=lambda r: r["ended_at"])
                self.assertEqual(recent["session_id"], expected)
                self.assertEqual(recent["session_id"], dispatch.read_runs(self.root / "runs.jsonl")[-1]["session"] or "")
                self.assertFalse(board.snapshot()[0])

    def test_manual_lifecycle_and_invalid_ids(self):
        lane = self.start()
        board.update(lane, doing="复核修改")
        running, ended = board.snapshot()
        self.assertEqual((len(running), ended), (1, []))
        self.assertEqual(running[0]["doing"], "复核修改")
        board.update(lane, status="failed")
        self.assertEqual(board.snapshot()[1][0]["status"], "failed")
        for target in (lane, "missing"):
            with self.assertRaises(ValueError):
                board.update(target, doing="不能复活")
        with self.assertRaises(ValueError):
            self.start(pid=0)

    def test_parallel_process_writes_do_not_lose_records(self):
        script = Path(dispatch.__file__)
        # Same name is valid; stable unique IDs prevent concurrent lanes colliding.
        argv = [sys.executable, str(script), "start", "--name", "共享车道名", "--doing", "并发写入" * 1000,
                "--tool", "other-cli", "--model", "m", "--effort", "none", "--pid", str(os.getpid()),
                "--cwd", str(self.root), "--task-dir", str(self.root)]
        procs = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(12)]
        ids = []
        for proc in procs:
            out, err = proc.communicate(timeout=20)
            self.assertEqual(proc.returncode, 0, err)
            ids.append(out.strip())
        self.assertEqual(len(set(ids)), 12)
        self.assertEqual({r["id"] for r in json.loads(self.path.read_text())["lanes"]}, set(ids))

    def test_pid_death_freezes_duration_at_last_update_without_writing(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            lane = self.start(pid=proc.pid)
            self.assertTrue(board.alive(proc.pid))
            def older(lanes):
                lanes[0]["started_at"] = "2026-01-01T00:00:00+00:00"
                lanes[0]["updated_at"] = "2026-01-01T00:00:17+00:00"
            board.mutate(older)
        finally:
            proc.kill()
            proc.wait(timeout=5)
        before = self.path.read_bytes()
        for _ in range(2):
            running, ended = board.snapshot()
            self.assertFalse(running)
            self.assertEqual(ended[0]["id"], lane)
            self.assertEqual(ended[0]["status"], "aborted")
            self.assertEqual(ended[0]["elapsed_seconds"], 17)
        self.assertEqual(before, self.path.read_bytes())
        self.assertFalse(board.alive(proc.pid))
        self.assertFalse(board.alive(-1))
        if os.name != "nt":
            with patch.object(board.os, "kill", side_effect=PermissionError):
                self.assertTrue(board.alive(123))

    def test_last_20_sorted_by_end_time_and_running_kept(self):
        live = self.start()
        for i in range(25):
            with patch.object(board, "stamp", return_value=f"2026-01-01T00:00:{i:02d}+00:00"):
                lane = self.start(name=str(i))
                board.update(lane, status=("ok", "failed", "aborted")[i % 3])
        running, ended = board.snapshot()
        self.assertEqual([r["id"] for r in running], [live])
        self.assertEqual([r["name"] for r in ended], list(map(str, range(24, 4, -1))))
        self.assertEqual(len(json.loads(self.path.read_text())["lanes"]), 21)

    def test_same_timestamp_history_keeps_latest_insertions(self):
        with patch.object(board, "stamp", return_value="2026-01-01T00:00:00+00:00"):
            for i in range(23):
                lane = self.start(name=str(i))
                board.update(lane, status="ok")
        self.assertEqual({r["name"] for r in board.snapshot()[1]}, set(map(str, range(3, 23))))

    def test_user_strings_cannot_break_out_of_embedded_data(self):
        doing = "{{DATA}} </script><b>检查</b> & <!--"
        self.start(doing=doing)
        page = board.render()
        self.assertNotIn("</script><b>", page)
        self.assertNotIn("<!--", page)
        self.assertIn("{{DATA}} \\u003c/script\\u003e\\u003cb\\u003e检查", page)
        self.assertEqual(self.payload(page)["running"][0]["doing"], doing)

    def test_page_refresh_is_bounded_and_cannot_stall(self):
        code = re.findall(r"<script>(.*?)</script>", board.template(), re.S)[0]
        consts = {k: float(v) for k, v in re.findall(r"\b(POLL_MS|FETCH_MS) = ([0-9.]+e3)", code)}
        self.assertLess(consts["FETCH_MS"], consts["POLL_MS"])
        self.assertIn("new AbortController()", code)
        self.assertIn("signal: pull.signal", code)
        self.assertRegex(code, r"finally \{[^}]*setTimeout\(poll, POLL_MS\)")

    def test_bad_json_is_not_overwritten(self):
        self.path.write_text("broken")
        with self.assertRaises(ValueError):
            self.start()
        self.assertEqual(self.path.read_text(), "broken")

    def test_xdg_location(self):
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.root)}, clear=True):
            self.assertEqual(board.state_path(), self.root / "dispatch/board.json")

    def test_xdg_board_and_runs_share_directory(self):
        env = dict(os.environ, XDG_STATE_HOME=str(self.root))
        for name in ("DISPATCH_BOARD_STATE", "DISPATCH_ROOT", "DISPATCH_RUNS"):
            env.pop(name, None)
        code = ("import json,board,dispatch; "
                "print(json.dumps([str(board.state_path()),str(dispatch.RUNS_FILE)]))")
        result = subprocess.run([sys.executable, "-c", code], cwd=Path(dispatch.__file__).parent,
                                env=env, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout),
                         [str(self.root / "dispatch/board.json"), str(self.root / "dispatch/runs.jsonl")])

    def test_last_update_visible_on_every_card_and_limit_from_constant(self):
        self.start()
        ended = self.start()
        board.update(ended, status="ok")
        def older(lanes):
            for lane in lanes:
                lane["updated_at"] = "2026-01-01T00:00:00+00:00"
        board.mutate(older)
        now = board.epoch("2026-01-01T00:07:30+00:00")
        with patch.object(board.time, "time", return_value=now), patch.object(board, "HISTORY_LIMIT", 7):
            data = self.payload(board.render())
        self.assertEqual(data["now"], now)
        self.assertEqual(data["history_limit"], 7)
        lanes = data["running"] + data["ended"]
        self.assertEqual([lane["updated_ago_seconds"] for lane in lanes], [450, 450])
        self.assertTrue(all(lane["updated_at"] == "2026-01-01T00:00:00+00:00" for lane in lanes))

    def test_tailscale_default_and_failure_has_explicit_host_hint(self):
        with patch.object(board.subprocess, "run") as run:
            run.return_value.stdout = "100.101.102.103\n"
            self.assertEqual(board.tailscale_host(), "100.101.102.103")
            for output in ("", "garbage", "0.0.0.0", "127.0.0.1"):
                run.return_value.stdout = output
                with self.assertRaisesRegex(ValueError, "--host"):
                    board.tailscale_host()
        with patch.object(board.subprocess, "run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValueError, "--host"):
                board.tailscale_host()

    def test_tailscale_names_use_only_self_and_strip_trailing_dots(self):
        status = {"Self": {"DNSName": "Worker.Mesh-Test.ts.net.", "HostName": "Worker."},
                  "Peer": {"other": {"DNSName": "other.mesh-test.ts.net."}}}
        with patch.object(board.subprocess, "run") as run:
            run.return_value.stdout = json.dumps(status)
            self.assertEqual(board.tailscale_names(), ["worker", "worker.mesh-test.ts.net"])
            self.assertEqual(run.call_args.args[0], ["tailscale", "status", "--json"])
            status["Self"]["HostName"] = "Raw OS Name"
            run.return_value.stdout = json.dumps(status)
            self.assertEqual(board.tailscale_names(), ["worker", "worker.mesh-test.ts.net"])
            run.return_value.stdout = json.dumps({"Self": {"HostName": "fallback"}})
            self.assertEqual(board.tailscale_names(), ["fallback"])

    def test_tailscale_name_discovery_failure_is_optional(self):
        with patch.object(board.subprocess, "run") as run, contextlib.redirect_stderr(io.StringIO()) as errors:
            for value in ("not json", "{}", '{"Self": null}'):
                run.return_value.stdout = value
                self.assertEqual(board.tailscale_names(), [])
            run.side_effect = FileNotFoundError("tailscale")
            self.assertEqual(board.tailscale_names(), [])
        self.assertIn("--allow-host", errors.getvalue())

    def test_default_server_announces_name_urls_before_ip(self):
        def tailscale(argv, **kwargs):
            result = subprocess.CompletedProcess(argv, 0)
            result.stdout = ("100.101.102.103\n" if argv[1:] == ["ip", "-4"] else
                             json.dumps({"Self": {"DNSName": "worker.mesh-test.ts.net.", "HostName": "worker"}}))
            return result
        with patch.object(board.subprocess, "run", side_effect=tailscale), patch.object(board, "Server") as server, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            instance = server.return_value.__enter__.return_value
            instance.urls = ["http://worker:18743/", "http://worker.mesh-test.ts.net:18743/",
                             "http://alias:18743/", "http://100.101.102.103:18743/"]
            instance.serve_forever.side_effect = KeyboardInterrupt
            board.serve(None, 18743, ["alias"])
            server.assert_called_once_with(("100.101.102.103", 18743), board.Handler,
                                           ["worker", "worker.mesh-test.ts.net", "alias"])
        self.assertEqual(out.getvalue().splitlines()[0], "Dispatch board: http://worker:18743/")
        self.assertIn("http://100.101.102.103:18743/", out.getvalue())

    def test_explicit_bind_does_not_discover_tailscale_and_cli_allows_repeats(self):
        args = dispatch.build_parser().parse_args([
            "board", "--host", "127.0.0.1", "--allow-host", "alias", "--allow-host", "other.example"])
        with patch.object(board, "serve") as serve:
            args.func(args)
            serve.assert_called_once_with("127.0.0.1", board.DEFAULT_PORT, ["alias", "other.example"])
        with patch.object(board.subprocess, "run") as run, patch.object(board, "Server") as server, \
                contextlib.redirect_stdout(io.StringIO()):
            server.return_value.__enter__.return_value.serve_forever.side_effect = KeyboardInterrupt
            board.serve("127.0.0.1", 18743, ["alias"])
            run.assert_not_called()

    def test_hostname_allowlist_accepts_exact_names_with_same_port_only(self):
        server = board.Server(("127.0.0.1", 0), board.Handler,
                              ["worker", "worker.mesh-test.ts.net.", "Alias", "alias"])
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_port
            self.assertEqual(server.urls, [f"http://worker:{port}/", f"http://worker.mesh-test.ts.net:{port}/",
                                          f"http://alias:{port}/", f"http://127.0.0.1:{port}/"])
            for host, expected in ((f"worker:{port}", 200), (f"WORKER:{port}", 200),
                                   (f"worker.mesh-test.ts.net:{port}", 200), (f"alias:{port}", 200),
                                   (f"127.0.0.1:{port}", 200), ("worker", 400), ("worker:1", 400),
                                   (f"other.mesh-test.ts.net:{port}", 400),
                                   (f"worker.attacker.example:{port}", 400)):
                with self.subTest(host=host):
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                    try:
                        connection.request("GET", "/", headers={"Host": host})
                        response = connection.getresponse()
                        self.assertEqual(response.status, expected)
                        response.read()
                    finally:
                        connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        for value in ("", "http://worker", "worker:18743", "*.example", "worker/path", "worker\r\nHeader: value"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                board.Server(("127.0.0.1", 0), board.Handler, [value])

    def test_http_read_only_and_escapes_fields(self):
        self.start(name='<script>alert("x")</script>', doing="审查 & 复核", effort="high")
        server = board.Server(("127.0.0.1", 0), board.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            origin = f"http://127.0.0.1:{server.server_port}"
            before = self.path.read_bytes()
            with urlopen(origin + "/") as response:
                page = response.read().decode()
                self.assertIn("\\u003cscript\\u003ealert", page)
                self.assertNotIn('<script>alert', page)
                self.assertEqual(self.payload(page)["running"][0]["effort"], "high")
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                policy = response.headers["Content-Security-Policy"]
                code = re.findall(r"<script>(.*?)</script>", page, re.S)
                self.assertEqual(len(code), 1)
                digest = base64.b64encode(hashlib.sha256(code[0].encode()).digest()).decode()
                self.assertIn(f"script-src 'sha256-{digest}';", policy)
                self.assertIn("connect-src 'self'", policy)
                self.assertNotIn("unsafe", policy.split("script-src ")[1].split(";")[0])
                for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
                    self.assertNotIn(sink, code[0])
            for request, code in ((origin + "/board.json", 404), (Request(origin + "/", data=b"write"), 501)):
                with self.assertRaises(HTTPError) as exc:
                    urlopen(request)
                self.assertEqual(exc.exception.code, code)
            self.assertEqual(before, self.path.read_bytes())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_http_host_must_match_including_port_for_all_methods(self):
        server = board.Server(("127.0.0.1", 0), board.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            expected = f"127.0.0.1:{server.server_port}"
            for method, hosts in (("GET", []), ("GET", ["untrusted.invalid"]),
                                  ("GET", ["127.0.0.1:1"]), ("GET", [expected, expected]),
                                  ("POST", ["untrusted.invalid"]), ("HEAD", ["untrusted.invalid"])):
                with self.subTest(method=method, hosts=hosts):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                    try:
                        connection.putrequest(method, "/", skip_host=True)
                        for host in hosts:
                            connection.putheader("Host", host)
                        connection.endheaders()
                        response = connection.getresponse()
                        self.assertEqual(response.status, 400)
                        response.read()
                    finally:
                        connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_board_failures_warn_and_do_not_block_run(self):
        prompt = self.root / "prompt.txt"
        prompt.write_text("test")
        args = dispatch.build_parser().parse_args([
            "run", "--name", "lane", "--doing", "检查", "--agent", "codex", "--model", "chosen",
            "--effort", "high", "--task-dir", str(self.root / "task"), "--cwd", str(self.root),
            "--prompt-file", str(prompt)])
        future_state = '{"version": 2, "lanes": []}'
        self.path.write_text(future_state)
        def fake_execute(cmd, cwd, event_path, stderr_path, merge_stderr):
            event_path.write_text('{"type":"turn.completed"}\n')
            return 0
        errors = io.StringIO()
        with patch.object(dispatch, "RUNS_FILE", self.root / "runs.jsonl"), \
                patch.object(dispatch, "execute", side_effect=fake_execute) as execute, \
                patch.object(dispatch.signal, "signal"), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(errors):
            self.assertEqual(dispatch.command_run(args), 0)
            for error in (PermissionError("read-only"), KeyError("bad lane")):
                with patch.object(board, "start", side_effect=error):
                    self.assertEqual(dispatch.command_run(args), 0)
            self.assertEqual(execute.call_count, 3)
        self.assertEqual(self.path.read_text(), future_state)
        self.assertIn("unsupported board state format", errors.getvalue())
        self.assertIn("warning:", errors.getvalue())
        records = dispatch.read_runs(self.root / "runs.jsonl")
        self.assertEqual(len(records), 3)
        self.assertTrue(all(record["status"] == "ok" for record in records))

    def test_board_update_failure_does_not_change_run_result(self):
        prompt = self.root / "prompt.txt"
        prompt.write_text("test")
        args = dispatch.build_parser().parse_args([
            "run", "--name", "lane", "--doing", "检查", "--agent", "codex", "--model", "chosen",
            "--effort", "high", "--task-dir", str(self.root / "task"), "--cwd", str(self.root),
            "--prompt-file", str(prompt)])
        attempted = threading.Event()
        def broken_update(**kwargs):
            attempted.set()
            raise KeyError("broken state")
        def fake_execute(cmd, cwd, event_path, stderr_path, merge_stderr):
            self.assertTrue(attempted.wait(2), "heartbeat did not attempt an update")
            event_path.write_text('{"type":"turn.completed"}\n')
            return 0
        errors = io.StringIO()
        with patch.object(dispatch, "RUNS_FILE", self.root / "runs.jsonl"), \
                patch.object(dispatch, "execute", side_effect=fake_execute), \
                patch.object(dispatch.signal, "signal"), patch.object(board, "HEARTBEAT_SECONDS", .01), \
                patch.object(board, "update", side_effect=broken_update) as update, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
            self.assertEqual(dispatch.command_run(args), 0)
            self.assertEqual(update.call_count, 2)  # heartbeat and finish both warn
        self.assertEqual(errors.getvalue().count("warning:"), 2)
        self.assertEqual(dispatch.read_runs(self.root / "runs.jsonl")[0]["status"], "ok")
        with self.assertRaises(dispatch.Terminated):
            dispatch.board_write(lambda: (_ for _ in ()).throw(dispatch.Terminated()))

    def test_run_auto_registers_heartbeats_and_finishes(self):
        prompt = self.root / "prompt.txt"
        prompt.write_text("test")
        args = dispatch.build_parser().parse_args([
            "run", "--name", "lane", "--doing", "检查", "--agent", "codex", "--model", "selected",
            "--effort", "medium", "--task-dir", str(self.root / "task"),
            "--cwd", str(self.root), "--prompt-file", str(prompt), "--resume", "session", "--issue", "https://example.com/task"])
        cases = [(0, '{"type":"turn.completed"}', "ok"), (1, '', "failed"),
                 (0, '', "failed"), (-9, '', "aborted"), (dispatch.Terminated(), '', "aborted")]
        for rc, event, expected in cases:
            def fake_execute(cmd, cwd, event_path, stderr_path, merge_stderr):
                running, _ = board.snapshot()
                self.assertEqual(len(running), 1)
                self.assertEqual(running[0]["pid"], os.getpid())
                self.assertEqual(running[0]["effort"], "medium")
                self.assertEqual(running[0]["model"], "selected")
                self.assertIn("resume", cmd)
                self.assertEqual(running[0]["issues"], ["https://example.com/task"])
                board.update(running[0]["id"], doing="阶段二")
                # Observe heartbeat without relying on a clock tick's wall time.
                deadline = time.monotonic() + 2
                while len(updates) < 2 and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertGreaterEqual(len(updates), 2)
                event_path.write_text(event + "\n")
                if isinstance(rc, Exception):
                    raise rc
                return rc
            updates = []
            original = board.update
            def track(*a, **kw):
                updates.append((a, kw))
                return original(*a, **kw)
            with patch.object(dispatch, "RUNS_FILE", self.root / "runs.jsonl"), \
                    patch.object(dispatch, "execute", side_effect=fake_execute), \
                    patch.object(dispatch.signal, "signal"), patch("builtins.print"), \
                    patch.object(board, "HEARTBEAT_SECONDS", .01), patch.object(board, "update", side_effect=track):
                result = dispatch.command_run(args)
            running, ended = board.snapshot()
            self.assertFalse(running)
            # timestamps can tie within a second, locate the just-created lane by ledger ID.
            record = dispatch.read_runs(self.root / "runs.jsonl")[-1]
            recent = next(r for r in ended if r["id"] == record["run_id"])
            self.assertEqual(recent["status"], expected)
            self.assertEqual(recent["doing"], "阶段二")
            self.assertEqual(result == 0, expected == "ok")

    def test_agy_requires_explicit_none_and_registers_it(self):
        prompt = self.root / "prompt.txt"
        prompt.write_text("test")
        argv = ["run", "--name", "lane", "--doing", "检查", "--agent", "agy", "--model", "selected",
                "--effort", "none", "--task-dir", str(self.root / "task"),
                "--cwd", str(self.root), "--prompt-file", str(prompt)]
        def fake_execute(cmd, cwd, event_path, stderr_path, merge_stderr):
            self.assertEqual(board.snapshot()[0][0]["effort"], "none")
            self.assertNotIn("--effort", cmd)
            event_path.write_text('{"event":"result","result":{"status":"SUCCESS","response":"ok"}}\n')
            return 0
        with patch.object(dispatch, "RUNS_FILE", self.root / "runs.jsonl"), \
                patch.object(dispatch, "execute", side_effect=fake_execute) as execute, \
                patch.object(dispatch.signal, "signal"), patch("builtins.print"):
            self.assertEqual(dispatch.command_run(dispatch.build_parser().parse_args(argv)), 0)
            argv[argv.index("--effort") + 1] = "high"
            with self.assertRaisesRegex(ValueError, "--effort none"):
                dispatch.command_run(dispatch.build_parser().parse_args(argv))
            execute.assert_called_once()

    def test_none_not_forwarded_to_tools_without_effort_control(self):
        cmd = dispatch.ADAPTERS["cmd"].build_command(prompt="test", model="m", effort="none",
                resume=None, event_path=Path("e"), result_path=Path("r"))
        self.assertNotIn("--effort", cmd)
        agy = dispatch.ADAPTERS["agy"].build_command(prompt="test", model="m", effort="none",
                resume=None, event_path=Path("e"), result_path=Path("r"))
        self.assertNotIn("--effort", agy)


if __name__ == "__main__":
    unittest.main()
