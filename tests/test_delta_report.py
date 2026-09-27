"""Delta math, record validation (rule 5 enforcement), report rendering."""

import unittest

from skillproof import record
from skillproof.delta import compute
from skillproof.errors import SPError
from skillproof.report import render
from tests.common import Base


def rec(arm="baseline", outcome="pass", reason=None, checks=None,
        tokens=(10, 5), duration=100):
    if tokens is None:
        metrics = {"tokens_in": None, "tokens_out": None, "model": None,
                   "reported": False}
    else:
        metrics = {"tokens_in": tokens[0], "tokens_out": tokens[1],
                   "model": "m", "reported": True}
    return {
        "arm": arm, "outcome": outcome, "reason_code": reason,
        "checks": checks if checks is not None else
            [{"id": "checks[0]", "type": "file_exists", "outcome": "pass",
              "detail": "d", "duration_ms": 1}],
        "agent": {"exit_code": 0, "timed_out": False, "exec_error": None,
                  "duration_ms": duration},
        "metrics": metrics,
        "side_effects": {"files_added": [], "files_removed": [],
                         "files_modified": [], "agent_workspace_sha256": "a" * 64,
                         "snapshot_truncated": False, "files_after": {}},
        "caps": {"task_timeout_s": 10, "max_output_bytes": 100,
                 "token_budget": None, "flags": []},
        "provenance": {"prompt_sha256": "b" * 64, "prompt_file": "raw/x",
                       "workspace": "raw/ws",
                       "post_check_workspace_sha256": "c" * 64,
                       "skill_sha256": None if arm == "baseline" else "d" * 64},
    }


class DeltaMath(unittest.TestCase):
    def test_shifts(self):
        self.assertEqual(compute(rec(), rec(outcome="fail"))["outcome_shift"],
                         "pass->fail")
        self.assertEqual(compute(rec(outcome="fail"), rec())["outcome_shift"],
                         "fail->pass")
        d = compute(rec(), rec(outcome="unknown", reason="agent_timeout"))
        self.assertEqual(d["outcome_shift"], "pass->unknown")

    def test_improvement_and_regression_flags(self):
        self.assertTrue(compute(rec(outcome="fail"), rec())["improvement"])
        self.assertTrue(compute(rec(), rec(outcome="fail"))["regression"])
        self.assertFalse(compute(rec(), rec())["regression"])

    def test_check_token_duration_deltas(self):
        b = rec(checks=[{"id": "c0", "type": "t", "outcome": "fail", "detail": "",
                         "duration_ms": 0},
                        {"id": "c1", "type": "t", "outcome": "pass", "detail": "",
                         "duration_ms": 0}], tokens=(100, 50), duration=200)
        t = rec(checks=[{"id": "c0", "type": "t", "outcome": "pass", "detail": "",
                         "duration_ms": 0},
                        {"id": "c1", "type": "t", "outcome": "pass", "detail": "",
                         "duration_ms": 0}], tokens=(160, 90), duration=350)
        d = compute(b, t)
        self.assertEqual(d["checks_pass_delta"], 1)
        self.assertEqual(d["tokens_delta"], 100)
        self.assertEqual(d["duration_delta_ms"], 150)

    def test_null_deltas_when_not_reported(self):
        b = rec(tokens=None)
        d = compute(b, rec())
        self.assertIsNone(d["tokens_delta"])


class RecordValidation(Base):
    def setUp(self):
        super().setUp()
        run_dict, _, _ = self.load_and_run(mode="write-on-skill")
        self.run_dict = run_dict

    def test_real_run_validates(self):
        self.assertEqual(record.validate_run(self.run_dict), [])

    def test_missing_provenance_field_rejected(self):
        del self.run_dict["tasks"][0]["baseline"]["provenance"]["prompt_sha256"]
        violations = record.validate_run(self.run_dict)
        self.assertTrue(any("prompt_sha256" in v for v in violations))
        with self.assertRaises(SPError) as ctx:
            record.assert_valid(self.run_dict)
        self.assertEqual(ctx.exception.code, "invalid_run")

    def test_provenance_block_removed_rejected(self):
        del self.run_dict["tasks"][0]["treatment"]["provenance"]
        violations = record.validate_run(self.run_dict)
        self.assertTrue(any("provenance" in v for v in violations))

    def test_unknown_without_reason_rejected(self):
        rec0 = self.run_dict["tasks"][0]["baseline"]
        rec0["outcome"] = "unknown"
        rec0["reason_code"] = None
        self.assertTrue(any("reason_code" in v
                            for v in record.validate_run(self.run_dict)))

    def test_missing_arm_rejected(self):
        del self.run_dict["tasks"][0]["treatment"]
        violations = record.validate_run(self.run_dict)
        self.assertTrue(any("treatment" in v for v in violations))

    def test_missing_limits_rejected(self):
        self.run_dict["limits"] = []
        self.assertTrue(any("limits" in v
                            for v in record.validate_run(self.run_dict)))


class ReportRendering(Base):
    def test_render_contains_key_sections(self):
        run_dict, _, _ = self.load_and_run(mode="write-on-skill")
        md = render(run_dict)
        for marker in ("# SkillProof delta report", run_dict["run_id"],
                       "## Arm summary", "## Per-task deltas",
                       "## Limits", "fail->pass", "skillproof.delta-report/0.1"):
            self.assertIn(marker, md)

    def test_render_marks_unreported_tokens_as_na(self):
        # bad-meta mode: agent self-report is unreadable -> tokens axes are n/a
        run_dict, _, _ = self.load_and_run(mode="bad-meta")
        md = render(run_dict)
        self.assertIn("n/a", md)


if __name__ == "__main__":
    unittest.main()
