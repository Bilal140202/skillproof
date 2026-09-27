"""verify: tamper evidence over committed runs."""

import json
import unittest

from skillproof.verify import verify_run
from tests.common import Base


class Verify(Base):
    def setUp(self):
        super().setUp()
        self.run_dict, self.exit_code, self.run_dir = self.load_and_run(
            mode="write-on-skill")

    def test_clean_run_verifies(self):
        problems, checked = verify_run(self.run_dir)
        self.assertEqual(problems, [])
        self.assertGreater(checked, 5)

    def test_tampered_workspace_detected(self):
        ws = self.run_dir / "raw" / "t001" / "treatment" / "workspace"
        (ws / "out.txt").write_text("tampered")
        problems, _ = verify_run(self.run_dir)
        self.assertTrue(any("treatment" in p and "workspace" in p for p in problems))

    def test_deleted_meta_json_detected(self):
        (self.run_dir / "raw" / "t001" / "baseline" / "meta.json").unlink()
        problems, _ = verify_run(self.run_dir)
        self.assertTrue(any("meta.json missing" in p for p in problems))

    def test_edited_meta_json_detected(self):
        f = self.run_dir / "raw" / "t001" / "baseline" / "meta.json"
        meta = json.loads(f.read_text())
        meta["outcome"] = "pass"  # edit history!
        f.write_text(json.dumps(meta))
        problems, _ = verify_run(self.run_dir)
        self.assertTrue(any("no longer matches" in p for p in problems))

    def test_tampered_inputs_detected(self):
        f = self.run_dir / "inputs" / "suite.json"
        doc = json.loads(f.read_text())
        doc["name"] = "rewritten-suite"
        f.write_text(json.dumps(doc))
        problems, _ = verify_run(self.run_dir)
        self.assertTrue(any("suite.json" in p for p in problems))

    def test_tampered_prompt_detected(self):
        f = self.run_dir / "raw" / "t001" / "treatment" / "prompt.txt"
        f.write_text("a different prompt entirely")
        problems, _ = verify_run(self.run_dir)
        self.assertTrue(any("prompt.txt" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
