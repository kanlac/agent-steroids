#!/usr/bin/env python3
"""Unit tests for dispatch.py using fragments of real event streams."""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import dispatch


def consume_all(adapter, lines):
    acc = adapter.new_acc()
    for line in lines:
        adapter.consume(acc, line)
    return acc


# --- fragments copied from real dispatch directories -----------------------

CODEX_OK = [
    '{"type":"thread.started","thread_id":"01a168a2-b3ce-7642-97ac-598b004b4de3"}',
    '{"type":"turn.started"}',
    '{"type":"item.completed","item":{"id":"item_105","type":"agent_message","text":"done"}}',
    '{"type":"turn.completed","usage":{"input_tokens":737227860,"cached_input_tokens":730437248,'
    '"cache_write_input_tokens":0,"output_tokens":2641175,"reasoning_output_tokens":1924701}}',
]

CODEX_CAPACITY = [
    '2026-10-26T15:05:36.657571Z ERROR rmcp::transport::worker: worker quit with fatal: Transport channel closed',
    '{"type":"thread.started","thread_id":"01a173de-7278-7303-97fa-00ebe7b5ad7b"}',
    '{"type":"error","message":"Selected model is at capacity. Please try a different model."}',
    '{"type":"turn.failed","error":{"message":"Selected model is at capacity. Please try a different model."}}',
]

AGY_OK = [
    '{"event":"init","conversation_id":"593e9f1d-21b7-4c07-862d-22ce8770a66d",'
    '"init":{"model":"gemini-4-argon-medium","cwd":"/home/user/work/lane-a"}}',
    '{"event":"step_update","step_update":{"conversation_id":"593e9f1d-21b7-4c07-862d-22ce8770a66d",'
    '"step_index":1,"state":"DONE","step_type":"agent_response","duration_seconds":5.683733,'
    '"usage":{"input_tokens":11083,"output_tokens":199,"thinking_tokens":0,'
    '"cache_read_tokens":0,"total_tokens":11282}}}',
    '{"event":"result","result":{"conversation_id":"593e9f1d-21b7-4c07-862d-22ce8770a66d",'
    '"status":"SUCCESS","response":"ok","duration_seconds":327.070759,"num_turns":1,'
    '"usage":{"input_tokens":185984,"output_tokens":10820,"thinking_tokens":0,'
    '"cache_read_tokens":2266730,"total_tokens":196804}}}',
]

AGY_ERROR = [
    AGY_OK[0],
    '{"event":"result","result":{"conversation_id":"4761b9dd-4c91-4d24-9af6-042da0c68341",'
    '"status":"ERROR","response":"boom","duration_seconds":10,"num_turns":1,'
    '"usage":{"input_tokens":100,"output_tokens":20,"thinking_tokens":0,'
    '"cache_read_tokens":0,"total_tokens":120}}}',
]

CMD_OK = [
    '{"type":"event","event":{"type":"run_start","sessionId":"9c696661-2b98-4c36-af01-cd13c8105001"}}',
    '{"type":"event","event":{"type":"turn_end","turnNumber":210,"hadToolCalls":false,'
    '"usage":{"inputTokens":383292,"outputTokens":1343,"cacheReadTokens":382976,"cacheWriteTokens":0}}}',
    '{"type":"result","subtype":"success","sessionId":"9c696661-2b98-4c36-af01-cd13c8105001",'
    '"stopReason":"end_turn","usage":{"inputTokens":54355441,"outputTokens":176265,'
    '"cacheReadTokens":53967744,"cacheWriteTokens":0},"durationMs":6748439,"finalText":"ok"}',
]

CMD_NO_RESULT = CMD_OK[:2]

CMD_MAX_TURNS = [
    CMD_OK[0],
    '{"type":"result","subtype":"max_turns","sessionId":"7188326d-b4d3-447e-9957-008eb467d3b2",'
    '"stopReason":"max_turns","usage":{"inputTokens":107630075,"outputTokens":201708,'
    '"cacheReadTokens":107138816,"cacheWriteTokens":0},"durationMs":5817118,'
    '"finalText":"Now the ink-based stem attachment for slash heads:"}',
]


class CodexTests(unittest.TestCase):
    def setUp(self):
        self.adapter = dispatch.ADAPTERS["codex"]

    def test_session_usage_status(self):
        acc = consume_all(self.adapter, CODEX_OK)
        self.assertEqual(acc["session"], "01a168a2-b3ce-7642-97ac-598b004b4de3")
        usage = self.adapter.usage(acc)
        self.assertEqual(usage["input"], 737227860 - 730437248)
        self.assertEqual(usage["cached"], 730437248)
        self.assertEqual(usage["output"], 2641175)
        self.assertEqual(usage["reasoning"], 1924701)
        self.assertEqual(usage["total"], usage["input"] + usage["cached"] + usage["output"])
        self.assertEqual(self.adapter.classify(acc, 0), "ok")

    def test_non_json_stderr_line_is_tolerated(self):
        acc = consume_all(self.adapter, CODEX_CAPACITY)
        self.assertEqual(acc["session"], "01a173de-7278-7303-97fa-00ebe7b5ad7b")
        self.assertIn("capacity", acc["flags"])

    def test_capacity_classification_and_auto_resume(self):
        acc = consume_all(self.adapter, CODEX_CAPACITY)
        self.assertEqual(self.adapter.classify(acc, 1), "capacity")
        decision = self.adapter.auto_resume(
            acc, 1, {"attempt": 0, "delay": 0, "max_attempts": self.adapter.max_retries})
        self.assertIsNotNone(decision)
        self.assertEqual(decision["reason"], "capacity")
        self.assertEqual(decision["session"], "01a173de-7278-7303-97fa-00ebe7b5ad7b")
        # six retries max
        self.assertIsNone(self.adapter.auto_resume(
            acc, 1, {"attempt": 6, "delay": 0, "max_attempts": self.adapter.max_retries}))

    def test_command_shape(self):
        cmd = self.adapter.build_command(
            prompt="hi", model="gpt-6.1-sol", effort="low", resume=None,
            event_path=Path("/tmp/e.jsonl"), result_path=Path("/tmp/r.md"),
        )
        self.assertEqual(cmd[1], "exec")
        self.assertIn("gpt-6.1-sol", cmd)
        self.assertIn("model_reasoning_effort=low", cmd)
        self.assertFalse(any("service_tier" in a for a in cmd))
        self.assertIn("--json", cmd)
        self.assertEqual(cmd[-1], "hi")

        resumed = self.adapter.build_command(
            prompt="go", model="m", effort="high", resume="sid",
            event_path=Path("/tmp/e.jsonl"), result_path=Path("/tmp/r.md"),
        )
        self.assertEqual(resumed[1:3], ["exec", "resume"])
        self.assertEqual(resumed[3], "sid")

    def test_combine_files_sums_attempts(self):
        second = (
            '{"type":"thread.started","thread_id":"01a168a2-b3ce-7642-97ac-598b004b4de3"}\n'
            '{"type":"turn.completed","usage":{"input_tokens":1000,"cached_input_tokens":400,'
            '"output_tokens":100,"reasoning_output_tokens":10}}\n'
        )
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "events-0.jsonl"
            p2 = Path(td) / "events-1.jsonl"
            p1.write_text("\n".join(CODEX_OK) + "\n")
            p2.write_text(second)
            combined = dispatch.combine_files([p1, p2], self.adapter, mode="full", cache=None)
            usage = combined["usage"]
            self.assertEqual(usage["input"], (737227860 - 730437248) + (1000 - 400))
            self.assertEqual(usage["cached"], 730437248 + 400)
            self.assertEqual(usage["output"], 2641175 + 100)
            self.assertEqual(usage["reasoning"], 1924701 + 10)


class AgyTests(unittest.TestCase):
    def setUp(self):
        self.adapter = dispatch.ADAPTERS["agy"]

    def test_session_usage_status(self):
        acc = consume_all(self.adapter, AGY_OK)
        self.assertEqual(acc["session"], "593e9f1d-21b7-4c07-862d-22ce8770a66d")
        self.assertEqual(acc["model"], "gemini-4-argon-medium")
        self.assertEqual(acc["cwd"], "/home/user/work/lane-a")
        usage = self.adapter.usage(acc)
        self.assertEqual(usage["input"], 185984)
        self.assertEqual(usage["cached"], 2266730)
        self.assertEqual(usage["output"], 10820)
        self.assertEqual(usage["total"], 2463534)
        self.assertEqual(self.adapter.classify(acc, 0), "ok")

    def test_error_status(self):
        acc = consume_all(self.adapter, AGY_ERROR)
        self.assertEqual(self.adapter.classify(acc, 0), "failed")

    def test_command_shape(self):
        cmd = self.adapter.build_command(
            prompt="hi", model="gemini-3.8-flash-low", effort="none", resume="conv",
            event_path=Path("/tmp/e.jsonl"), result_path=Path("/tmp/r.md"),
        )
        self.assertIn("--dangerously-skip-permissions", cmd)
        self.assertIn("stream-json", cmd)
        self.assertIn("--print-timeout", cmd)
        self.assertIn("0", cmd)
        self.assertIn("--conversation", cmd)


class CmdTests(unittest.TestCase):
    def setUp(self):
        self.adapter = dispatch.ADAPTERS["cmd"]

    def test_session_and_final_usage(self):
        acc = consume_all(self.adapter, CMD_OK)
        self.assertEqual(acc["session"], "9c696661-2b98-4c36-af01-cd13c8105001")
        self.assertTrue(acc["has_result_line"])
        usage = self.adapter.usage(acc)
        self.assertEqual(usage["input"], 54355441 - 53967744)
        self.assertEqual(usage["cached"], 53967744)
        self.assertEqual(usage["output"], 176265)
        self.assertEqual(self.adapter.classify(acc, 0), "ok")

    def test_partial_usage_and_no_result_resume(self):
        acc = consume_all(self.adapter, CMD_NO_RESULT)
        self.assertEqual(acc["session"], "9c696661-2b98-4c36-af01-cd13c8105001")
        usage = self.adapter.usage(acc)
        self.assertEqual(usage["input"], 383292 - 382976)
        self.assertEqual(usage["cached"], 382976)
        self.assertEqual(usage["output"], 1343)
        self.assertEqual(self.adapter.classify(acc, 0), "no_result")
        decision = self.adapter.auto_resume(
            acc, 0, {"attempt": 0, "delay": 0, "max_attempts": self.adapter.max_retries})
        self.assertIsNotNone(decision)
        self.assertEqual(decision["reason"], "no_result")
        self.assertIsNone(self.adapter.auto_resume(
            acc, 0, {"attempt": 3, "delay": 0, "max_attempts": self.adapter.max_retries}))

    def test_max_turns(self):
        acc = consume_all(self.adapter, CMD_MAX_TURNS)
        self.assertEqual(self.adapter.classify(acc, 0), "max_turns")

    def test_command_shape(self):
        cmd = self.adapter.build_command(
            prompt="hi", model="deepseek/deepseek-v4.1-flash", effort="high", resume="sid",
            event_path=Path("/tmp/e.jsonl"), result_path=Path("/tmp/r.md"),
        )
        for flag in ("--yolo", "--trust", "--skip-onboarding", "--no-auto-update", "--output-format", "json"):
            self.assertIn(flag, cmd)
        self.assertIn("--max-turns", cmd)
        self.assertIn("1500", cmd)
        self.assertIn("--resume", cmd)
        self.assertEqual(cmd[cmd.index("--effort") + 1], "high")

    def test_runner_forwards_effort_and_records_it(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            task_dir = root / "task"
            prompt_file = root / "prompt.txt"
            prompt_file.write_text("hi", encoding="utf-8")
            runs_file = root / "runs.jsonl"
            model = "deepseek/deepseek-v4.1-flash"
            args = dispatch.build_parser().parse_args([
                "run", "--name", "effort regression", "--agent", "cmd",
                "--task-dir", str(task_dir), "--cwd", str(root),
                "--prompt-file", str(prompt_file), "--model", model,
                "--effort", "high", "--doing", "验证强度传递",
            ])

            def fake_execute(cmd, cwd, event_path, stderr_path, merge_stderr):
                event_path.write_text("\n".join(CMD_OK) + "\n", encoding="utf-8")
                return 0

            with patch.dict(os.environ, {"DISPATCH_BOARD_DIR": str(root / "boards"), "DISPATCH_BOARD_STATE": str(root / "board.json"), "DISPATCH_BOARD": "test-board"}), \
                    patch.object(dispatch, "RUNS_FILE", runs_file), \
                    patch.object(dispatch, "execute", side_effect=fake_execute) as execute, \
                    patch.object(dispatch.signal, "signal"), patch("builtins.print"):
                dispatch.command_run(args)

            execute.assert_called_once()
            argv = execute.call_args.args[0]
            self.assertEqual(argv[argv.index("--effort") + 1], "high")
            self.assertEqual(argv[argv.index("-m") + 1], model)
            records = [json.loads(line) for line in runs_file.read_text().splitlines()]
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["effort"], "high")
            self.assertEqual(records[0]["model"], model)
            self.assertEqual(records[1]["run_id"], records[0]["run_id"])
            self.assertEqual(records[1]["status"], "ok")


class MiscTests(unittest.TestCase):
    def test_alias_is_stable(self):
        a = dispatch.alias_for(Path("/tmp/some/task"))
        b = dispatch.alias_for(Path("/tmp/some/task"))
        self.assertEqual(a, b)
        self.assertIn("·", a)

    def test_legacy_family_patterns(self):
        cases = {
            "events-16.jsonl": "codex",
            "events-agy-0.jsonl": "agy",
            "events-cmd-3.jsonl": "cmd",
        }
        for name, expected in cases.items():
            found = [k for k, rx in dispatch.LEGACY_PATTERNS if rx.match(name)]
            self.assertEqual(found, [expected])
        self.assertFalse(any(rx.match("prompt.txt") for _, rx in dispatch.LEGACY_PATTERNS))

    def test_read_runs_merges_start_and_end(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "runs.jsonl"
            start = {
                "run_id": "r1", "name": "n", "alias": "a", "agent": "cmd",
                "model": "m", "effort": None, "task_dir": td, "cwd": td,
                "prompt_file": "p", "started_at": "2026-10-27T00:00:00+08:00", "resume_of": None,
            }
            end = {
                "run_id": "r1", "ended_at": "2026-10-27T00:01:00+08:00", "exit": 0,
                "status": "ok", "session": "s", "retries": 0,
                "usage": {"input": 1, "cached": 2, "output": 3, "reasoning": 0},
                "events_files": [],
            }
            path.write_text(json.dumps(start) + "\n" + json.dumps(end) + "\n")
            runs = dispatch.read_runs(path)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["status"], "ok")
            self.assertEqual(runs[0]["session"], "s")
            self.assertEqual(runs[0]["started_at"], start["started_at"])

    def test_cost_lookup(self):
        usage = {"input": 1_000_000, "cached": 1_000_000, "output": 1_000_000}
        prices = {"m": {"input": 3, "cached": 0.3, "output": 15}}
        self.assertAlmostEqual(dispatch.cost_of(usage, "m", prices), 18.3)
        self.assertIsNone(dispatch.cost_of(usage, "unknown", prices))

    def test_collect_rows_with_runs_and_legacy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "dispatch"
            root.mkdir()
            old = root / "old-task"
            old.mkdir()
            (old / "events-0.jsonl").write_text("\n".join(CODEX_OK) + "\n")
            (old / "exit.txt").write_text("0")

            live = root / "live-task"
            live.mkdir()
            runs_file = root / "runs.jsonl"
            started = dispatch.now_iso()
            start = {
                "run_id": "live1", "name": "live", "alias": "x", "agent": "cmd",
                "model": "deepseek/deepseek-v4.1-flash", "effort": None,
                "task_dir": str(live), "cwd": str(live), "prompt_file": "p",
                "started_at": started, "resume_of": None,
            }
            runs_file.write_text(json.dumps(start) + "\n")
            (live / "events-cmd-0.jsonl").write_text("\n".join(CMD_NO_RESULT) + "\n")

            rows, legacy, _ = dispatch.collect_rows(runs_file=runs_file, root=root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "running")
            self.assertEqual(rows[0]["usage"]["total"], (383292 - 382976) + 382976 + 1343)
            self.assertEqual(len(legacy), 1)
            self.assertEqual(legacy[0]["name"], "old-task")
            self.assertEqual(legacy[0]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
