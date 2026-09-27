"""CLI + demo end-to-end through the real entrypoint."""

import os
import unittest
from pathlib import Path

from skillproof.cli import main
from tests.common import Base


class Cli(Base):
    def test_version(self):
        self.assertEqual(main(["version"]), 0)

    def test_relative_out_root_resolves_paths(self):
        # Regression: with a relative --out, the agent subprocess used to get
        # relative {workspace}/{suite_dir} values and write outside the
        # workspace (first dogfood run found this).
        cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, cwd)
        suite = self.make_suite([self.default_task()])
        config = self.make_config(self.make_agent("write-on-skill"))
        self.make_skill()
        rc = main(["run", "--suite", str(suite), "--config", str(config),
                   "--skill", str(self.tmp / "skill"), "--out", "results"])
        self.assertEqual(rc, 0)
        run_json = next(Path("results").glob("*/run.json")).read_text()
        self.assertIn('"outcome_shift": "fail->pass"', run_json)
        # no stray junk tree inside the workspace (only the agent's own
        # self-report dir and the expected output)
        ws = next(Path("results").glob("*/raw/t001/treatment/workspace"))
        self.assertEqual(sorted(p.name for p in ws.iterdir()),
                         [".skillproof", "out.txt"])

    def test_run_report_verify_roundtrip(self):
        suite = self.make_suite([self.default_task()])
        config = self.make_config(self.make_agent("write-on-skill"))
        skill = self.make_skill()
        out = self.tmp / "results"
        rc = main(["run", "--suite", str(suite), "--config", str(config),
                   "--skill", str(skill), "--out", str(out)])
        self.assertEqual(rc, 0)
        run_dirs = list(out.iterdir())
        self.assertEqual(len(run_dirs), 1)
        run_dir = run_dirs[0]
        self.assertTrue((run_dir / "REPORT.md").is_file())
        self.assertTrue((run_dir / "run.json").is_file())

        self.assertEqual(main(["report", "--run", str(run_dir)]), 0)
        self.assertEqual(main(["verify", "--run", str(run_dir)]), 0)

    def test_missing_suite_is_exit_2(self):
        config = self.make_config(self.make_agent("write-both"))
        self.make_skill()
        rc = main(["run", "--suite", str(self.tmp / "ghost.json"),
                   "--config", str(config),
                   "--skill", str(self.tmp / "skill"), "--out", str(self.tmp / "r")])
        self.assertEqual(rc, 2)

    def test_full_demo_offline(self):
        out = self.tmp / "demo-out"
        self.assertEqual(main(["demo", "--out", str(out)]), 0)
        self.assertTrue((out / "demo" / "suite.json").is_file())
        results = list((out / "results").iterdir())
        self.assertEqual(len(results), 1)
        run_json = (results[0] / "run.json").read_text()
        # the demo's designed shapes, end to end
        self.assertIn('"outcome_shift": "fail->pass"', run_json)
        self.assertIn('"outcome_shift": "pass->fail"', run_json)
        self.assertIn("token_budget_exceeded", run_json)
        self.assertEqual(main(["verify", "--run", str(results[0])]), 0)

    def test_demo_creates_expected_report(self):
        out = self.tmp / "demo-out2"
        main(["demo", "--out", str(out)])
        report = next((out / "results").glob("*/REPORT.md")).read_text()
        self.assertIn("regressions (pass->fail): t004-count-line", report)
        self.assertIn("token_budget_exceeded", report)


if __name__ == "__main__":
    unittest.main()
