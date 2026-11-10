#!/usr/bin/env python3
"""Board contract tests. All state is isolated; no model CLI is launched."""
import contextlib
import io
import http.client
import json
import os
from pathlib import Path
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

    def test_user_template_markers_remain_literal(self):
        self.start(doing="{{ENDED}} <b>检查</b>")
        page = board.render()
        self.assertIn("{{ENDED}} &lt;b&gt;检查&lt;/b&gt;", page)

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
        with patch.object(board.time, "time", return_value=board.epoch("2026-01-01T00:07:30+00:00")), \
                patch.object(board, "HISTORY_LIMIT", 7):
            page = board.render()
        self.assertEqual(page.count("最后更新于 7 分钟前"), 2)
        self.assertIn("保留最近 7 条", page)
        self.assertNotIn("保留最近 20 条", page)

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
                self.assertIn("&lt;script&gt;", page)
                self.assertNotIn('<script>alert', page)
                self.assertIn('class="effort">high', page)
                self.assertIn('http-equiv="refresh" content="5"', page)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
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
            expected = server.expected_host
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
            "--cwd", str(self.root), "--prompt-file", str(prompt), "--resume", "session"])
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
