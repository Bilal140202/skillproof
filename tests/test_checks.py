"""Check engine: three-valued outcomes, fail-closed spec handling."""

import unittest

from skillproof import checks
from skillproof.config import Caps
from tests.common import Base

CAPS = Caps(task_timeout_s=10, run_timeout_s=60, max_output_bytes=65_536,
            token_budget=None, max_workspace_files=2000, max_file_bytes=1024)


def apply(spec, ws):
    return checks.apply_check(spec, 0, ws, CAPS)


class FileChecks(Base):
    def test_file_exists_pass_and_fail(self):
        (self.tmp / "a.txt").write_text("x")
        self.assertEqual(apply({"type": "file_exists", "path": "a.txt"},
                               self.tmp).outcome, "pass")
        self.assertEqual(apply({"type": "file_exists", "path": "nope.txt"},
                               self.tmp).outcome, "fail")

    def test_file_absent(self):
        self.assertEqual(apply({"type": "file_absent", "path": "nope"},
                               self.tmp).outcome, "pass")
        (self.tmp / "here").write_text("x")
        self.assertEqual(apply({"type": "file_absent", "path": "here"},
                               self.tmp).outcome, "fail")

    def test_file_contains_text(self):
        (self.tmp / "a.txt").write_text("hello world")
        ok = {"type": "file_contains", "path": "a.txt", "text": "world"}
        bad = {"type": "file_contains", "path": "a.txt", "text": "planet"}
        missing = {"type": "file_contains", "path": "ghost.txt", "text": "x"}
        self.assertEqual(apply(ok, self.tmp).outcome, "pass")
        self.assertEqual(apply(bad, self.tmp).outcome, "fail")
        # a missing file is a fail (evidence decided against), not an error
        self.assertEqual(apply(missing, self.tmp).outcome, "fail")
        self.assertIn("missing", apply(missing, self.tmp).detail)

    def test_file_contains_regex_and_ignorecase(self):
        (self.tmp / "a.txt").write_text("Hello World")
        rx = {"type": "file_contains", "path": "a.txt", "regex": "w.rld"}
        self.assertEqual(apply(rx, self.tmp).outcome, "fail")
        rx_ic = {"type": "file_contains", "path": "a.txt", "regex": "w.rld",
                 "ignorecase": True}
        self.assertEqual(apply(rx_ic, self.tmp).outcome, "pass")

    def test_file_too_big_is_error_not_fail(self):
        (self.tmp / "big.txt").write_text("x" * 2048)
        res = apply({"type": "file_contains", "path": "big.txt", "text": "x"},
                    self.tmp)
        self.assertEqual(res.outcome, "error")
        self.assertIn("ceiling", res.detail)


class JsonChecks(Base):
    def test_json_equals_pass_fail_nested(self):
        (self.tmp / "d.json").write_text('{"a": {"list": [1, 2, {"k": true}]}}')
        ok = {"type": "json_equals", "path": "d.json", "key": "a.list.2.k",
              "expected": True}
        self.assertEqual(apply(ok, self.tmp).outcome, "pass")
        wrong = {"type": "json_equals", "path": "d.json", "key": "a.list.0",
                 "expected": 2}
        self.assertEqual(apply(wrong, self.tmp).outcome, "fail")

    def test_json_bool_int_strictness(self):
        (self.tmp / "d.json").write_text('{"n": 1}')
        spec = {"type": "json_equals", "path": "d.json", "key": "n",
                "expected": True}
        self.assertEqual(apply(spec, self.tmp).outcome, "fail")

    def test_json_missing_key_and_invalid_json(self):
        (self.tmp / "bad.json").write_text("{not json")
        res = apply({"type": "json_equals", "path": "bad.json", "key": "a",
                     "expected": 1}, self.tmp)
        self.assertEqual(res.outcome, "fail")
        (self.tmp / "d.json").write_text('{"a": 1}')
        res2 = apply({"type": "json_equals", "path": "d.json", "key": "b",
                      "expected": 1}, self.tmp)
        self.assertEqual(res2.outcome, "fail")
        self.assertIn("not found", res2.detail)


class CommandChecks(Base):
    def test_command_ok_pass_fail(self):
        ok = {"type": "command_ok", "command": "true"}
        self.assertEqual(apply(ok, self.tmp).outcome, "pass")
        bad = {"type": "command_ok", "command": ["sh", "-c", "exit 3"]}
        self.assertEqual(apply(bad, self.tmp).outcome, "fail")

    def test_command_missing_binary_is_error(self):
        res = apply({"type": "command_ok",
                     "command": "definitely-not-a-binary-xyz --flag"}, self.tmp)
        self.assertEqual(res.outcome, "error")
        self.assertIn("failed to start", res.detail)

    def test_command_timeout_is_error(self):
        res = apply({"type": "command_ok", "command": "sleep 5", "timeout_s": 1},
                    self.tmp)
        self.assertEqual(res.outcome, "error")
        self.assertIn("timeout", res.detail)

    def test_command_stdout_contains_and_regex(self):
        ok = {"type": "command_stdout", "command": ["sh", "-c", "echo hello"],
              "contains": "ell"}
        self.assertEqual(apply(ok, self.tmp).outcome, "pass")
        rx = {"type": "command_stdout", "command": ["sh", "-c", "echo Hello"],
              "regex": "^hello$", "ignorecase": True}
        self.assertEqual(apply(rx, self.tmp).outcome, "pass")
        bad = {"type": "command_stdout", "command": ["sh", "-c", "echo hello"],
               "contains": "xyz"}
        self.assertEqual(apply(bad, self.tmp).outcome, "fail")

    def test_command_nonzero_fail_shows_stderr_tail(self):
        res = apply({"type": "command_stdout",
                     "command": ["sh", "-c", "echo boom >&2; exit 2"],
                     "contains": "x"}, self.tmp)
        self.assertEqual(res.outcome, "fail")
        self.assertIn("boom", res.detail)


class SpecHandling(Base):
    def test_unknown_check_type_is_error(self):
        res = apply({"type": "vibes", "score": 10}, self.tmp)
        self.assertEqual(res.outcome, "error")
        self.assertIn("unknown check type", res.detail)

    def test_unknown_field_is_error(self):
        res = apply({"type": "file_exists", "path": "a", "vibes": 1}, self.tmp)
        self.assertEqual(res.outcome, "error")
        self.assertIn("unknown field", res.detail)

    def test_missing_required_field_is_error(self):
        res = apply({"type": "file_exists"}, self.tmp)
        self.assertEqual(res.outcome, "error")
        self.assertIn("missing field", res.detail)

    def test_path_traversal_rejected(self):
        res = apply({"type": "file_exists", "path": "../escape"}, self.tmp)
        self.assertEqual(res.outcome, "error")
        self.assertIn("traverse", res.detail)

    def test_reserved_skillproof_prefix_rejected(self):
        res = apply({"type": "file_exists", "path": ".skillproof/agent_meta.json"},
                    self.tmp)
        self.assertEqual(res.outcome, "error")

    def test_check_never_raises(self):
        res = checks.apply_check("not a dict", 3, self.tmp, CAPS)
        self.assertEqual(res.outcome, "error")
        self.assertEqual(res.id, "checks[3]")


if __name__ == "__main__":
    unittest.main()
