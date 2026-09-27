"""Runner end-to-end: dual-arm pairing, outcome mapping, ceilings, evidence."""

import json
import unittest
from unittest import mock

from skillproof import runner
from skillproof.errors import SPError
from skillproof.verify import verify_run
from tests.common import Base


class PairedArms(Base):
    def test_improvement_fail_to_pass_with_full_provenance(self):
        run_dict, exit_code, run_dir = self.load_and_run(mode="write-on-skill")
        self.assertEqual(exit_code, 0)
        self.assertEqual(run_dict["run_status"], "complete")
        t = run_dict["tasks"][0]
        self.assertEqual(t["baseline"]["outcome"], "fail")
        self.assertEqual(t["treatment"]["outcome"], "pass")
        self.assertEqual(t["outcome_shift"], "fail->pass")
        self.assertTrue(t["improvement"])
        self.assertFalse(t["regression"])
        # provenance (rule 5): identical prompts, skill hash only on treatment
        self.assertEqual(t["baseline"]["provenance"]["prompt_sha256"],
                         t["treatment"]["provenance"]["prompt_sha256"])
        self.assertIsNone(t["baseline"]["provenance"]["skill_sha256"])
        self.assertIsNotNone(t["treatment"]["provenance"]["skill_sha256"])
        self.assertEqual(run_dict["provenance"]["skill"]["sha256"],
                         t["treatment"]["provenance"]["skill_sha256"])
        self.assertTrue(run_dict["limits"])  # rule 7
        problems, checked = verify_run(run_dir)
        self.assertEqual(problems, [])
        self.assertGreater(checked, 0)

    def test_neutral_and_metrics_delta(self):
        run_dict, exit_code, _ = self.load_and_run(
            mode="write-both",
            tasks=[self.default_task(
                checks=[{"type": "file_contains", "path": "out.txt",
                         "text": "done"}])])
        t = run_dict["tasks"][0]
        self.assertEqual(t["outcome_shift"], "pass->pass")
        self.assertEqual(t["checks_pass_delta"], 0)
        self.assertEqual(t["tokens_delta"], 0)  # same self-reported usage
        self.assertEqual(exit_code, 0)

    def test_agent_exit_code_does_not_decide_outcome(self):
        # agent exits 1 but produces the required file: checks decide (pass)
        run_dict, _, _ = self.load_and_run(mode="exit-nonzero-but-write")
        t = run_dict["tasks"][0]
        self.assertEqual(t["treatment"]["outcome"], "pass")
        self.assertEqual(t["treatment"]["agent"]["exit_code"], 1)

    def test_silent_agent_is_fail_not_unknown(self):
        run_dict, _, _ = self.load_and_run(mode="silent")
        t = run_dict["tasks"][0]
        self.assertEqual(t["baseline"]["outcome"], "fail")
        self.assertEqual(t["baseline"]["reason_code"], "checks_failed")

    def test_both_arms_always_present(self):
        run_dict, _, _ = self.load_and_run(mode="write-both")
        self.assertEqual(set(run_dict["tasks"][0]),
                         {"task_id", "baseline", "treatment", "outcome_shift",
                          "checks_pass_delta", "tokens_delta",
                          "duration_delta_ms", "improvement", "regression"})


class UnknownMapping(Base):
    def test_agent_timeout_is_unknown(self):
        run_dict, _, _ = self.load_and_run(
            mode="sleep",
            tasks=[self.default_task(timeout_s=1)])
        t = run_dict["tasks"][0]
        for arm in ("baseline", "treatment"):
            self.assertEqual(t[arm]["outcome"], "unknown")
            self.assertEqual(t[arm]["reason_code"], "agent_timeout")

    def test_agent_exec_error_is_unknown(self):
        # template points at a binary that cannot start
        suite_p = self.make_suite([self.default_task()])
        cfg_p = self.make_config(self.make_agent("write-both"))
        doc = json.loads(cfg_p.read_text())
        doc["adapter"]["command_template"] = \
            "/no/such/binary-xyz --workspace {workspace} --prompt-file {prompt_file}"
        cfg_p.write_text(json.dumps(doc))
        from skillproof.config import load_config
        from skillproof.skillbundle import load_skill
        from skillproof.suite import load_suite
        from skillproof import runner
        run_dict, _ = runner.run(load_suite(suite_p), load_config(cfg_p),
                                 load_skill(self.make_skill()), self.tmp / "results")
        t = run_dict["tasks"][0]
        self.assertEqual(t["baseline"]["outcome"], "unknown")
        self.assertEqual(t["baseline"]["reason_code"], "agent_exec_error")

    def test_token_budget_exceeded_is_unknown(self):
        run_dict, _, _ = self.load_and_run(
            mode="over-budget", caps={"token_budget": 20000},
            tasks=[self.default_task(
                checks=[{"type": "file_contains", "path": "out.txt",
                         "text": "done"}])])
        t = run_dict["tasks"][0]
        self.assertEqual(t["baseline"]["outcome"], "pass")  # 120 tokens, fine
        self.assertEqual(t["treatment"]["outcome"], "unknown")
        self.assertEqual(t["treatment"]["reason_code"], "token_budget_exceeded")
        self.assertEqual(t["outcome_shift"], "pass->unknown")

    def test_bad_agent_meta_is_ignored_with_flag(self):
        run_dict, _, _ = self.load_and_run(mode="bad-meta")
        rec = run_dict["tasks"][0]["treatment"]
        self.assertFalse(rec["metrics"]["reported"])
        self.assertTrue(any(str(f).startswith("agent_meta_note")
                            for f in rec["caps"]["flags"]))


class Ceilings(Base):
    def test_run_deadline_produces_explicit_aborted_report(self):
        run_dict, exit_code, run_dir = self.load_and_run(
            mode="sleep",
            tasks=[self.default_task(id="t001", timeout_s=10),
                   self.default_task(id="t002", timeout_s=10)],
            caps={"run_timeout_s": 1})
        self.assertEqual(exit_code, 1)
        self.assertEqual(run_dict["run_status"], "aborted")
        skipped = [t for t in run_dict["tasks"]
                   for arm in ("baseline", "treatment")
                   if t[arm]["reason_code"] == "run_deadline_exceeded"]
        self.assertTrue(skipped)  # explicit, labeled, never silent
        self.assertTrue((run_dir / "REPORT.md").is_file())
        self.assertTrue((run_dir / "run.json").is_file())

    def test_run_dir_never_overwritten(self):
        fixed = "20260101T000000Z-cafebabe"
        with mock.patch.object(runner.provenance, "make_run_id",
                               lambda parts: fixed):
            self.load_and_run(mode="write-both")
            with self.assertRaises(SPError) as ctx:
                self.load_and_run(mode="write-both")
        self.assertEqual(ctx.exception.code, "run_dir_exists")


class SideEffects(Base):
    def test_added_removed_modified_and_skillproof_excluded(self):
        task = self.default_task(
            setup={"seed.txt": "orig\n", "gone.txt": "bye\n"})
        run_dict, _, run_dir = self.load_and_run(
            mode="overwrite-setup", tasks=[task])
        rec = run_dict["tasks"][0]["treatment"]
        # agent overwrote the setup seed, deleted gone.txt, added nothing
        self.assertEqual(rec["side_effects"]["files_added"], [])
        self.assertEqual(rec["side_effects"]["files_removed"], ["gone.txt"])
        self.assertEqual(rec["side_effects"]["files_modified"], ["seed.txt"])
        # reserved self-report dir never leaks into the manifest
        self.assertFalse(any(p.startswith(".skillproof")
                             for p in rec["side_effects"]["files_after"]))
        # but raw evidence exists: prompt, agent log, meta, workspace snapshot
        arm_dir = run_dir / "raw" / "t001" / "treatment"
        self.assertTrue((arm_dir / "prompt.txt").is_file())
        self.assertTrue((arm_dir / "agent.log").is_file())
        self.assertTrue((arm_dir / "agent_meta.json").is_file())
        self.assertTrue((arm_dir / "workspace" / "seed.txt").is_file())

    def test_setup_manifest_records_modified_file(self):
        task = self.default_task(setup={"seed.txt": "orig\n"})
        run_dict, _, _ = self.load_and_run(mode="overwrite-setup", tasks=[task])
        rec = run_dict["tasks"][0]["baseline"]
        self.assertEqual(rec["side_effects"]["files_modified"], ["seed.txt"])


if __name__ == "__main__":
    unittest.main()
