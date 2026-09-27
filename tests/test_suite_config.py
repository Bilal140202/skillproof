"""Suite/config loaders: strict schemas, fail-closed validation."""

import json
import unittest

from skillproof.config import load_config
from skillproof.errors import SPError
from skillproof.suite import load_suite
from tests.common import Base


class SuiteLoading(Base):
    def test_valid_suite_loads_with_stable_hash(self):
        p = self.make_suite([self.default_task()])
        s1 = load_suite(p)
        s2 = load_suite(p)
        self.assertEqual(s1.name, "test-suite")
        self.assertEqual(len(s1.tasks), 1)
        self.assertEqual(s1.sha256, s2.sha256)

    def test_invalid_json_rejected(self):
        p = self.tmp / "suite.json"
        p.write_text("{nope")
        with self.assertRaises(SPError) as ctx:
            load_suite(p)
        self.assertEqual(ctx.exception.code, "bad_suite")

    def test_missing_file_rejected(self):
        with self.assertRaises(SPError) as ctx:
            load_suite(self.tmp / "ghost.json")
        self.assertEqual(ctx.exception.code, "missing_input")

    def test_wrong_schema_string(self):
        doc = {"schema": "skillproof.suite/9.9", "name": "x",
               "tasks": [self.default_task()]}
        p = self.tmp / "s.json"
        p.write_text(json.dumps(doc))
        with self.assertRaises(SPError):
            load_suite(p)

    def test_duplicate_task_ids(self):
        p = self.make_suite([self.default_task(), self.default_task()])
        with self.assertRaises(SPError) as ctx:
            load_suite(p)
        self.assertIn("duplicate", str(ctx.exception))

    def test_bad_task_id_charset(self):
        p = self.make_suite([self.default_task(id="T001!")])
        with self.assertRaises(SPError):
            load_suite(p)

    def test_empty_checks_rejected(self):
        p = self.make_suite([self.default_task(checks=[])])
        with self.assertRaises(SPError):
            load_suite(p)

    def test_unknown_check_type_rejected_at_load(self):
        p = self.make_suite([self.default_task(checks=[{"type": "vibes"}])])
        with self.assertRaises(SPError):
            load_suite(p)

    def test_unknown_task_field_rejected(self):
        p = self.make_suite([self.default_task(vibes="high")])
        with self.assertRaises(SPError):
            load_suite(p)

    def test_unknown_top_field_rejected(self):
        p = self.make_suite([self.default_task()])
        doc = json.loads(p.read_text())
        doc["vibes"] = 1
        p.write_text(json.dumps(doc))
        with self.assertRaises(SPError):
            load_suite(p)

    def test_setup_traversal_rejected(self):
        p = self.make_suite([self.default_task(setup={"../evil": "x"})])
        with self.assertRaises(SPError):
            load_suite(p)

    def test_setup_reserved_prefix_rejected(self):
        p = self.make_suite([self.default_task(setup={".skillproof/meta": "x"})])
        with self.assertRaises(SPError):
            load_suite(p)

    def test_setup_base64_and_bytes_roundtrip(self):
        import base64
        blob = base64.b64encode(b"\x00\x01binary").decode()
        p = self.make_suite([self.default_task(setup={
            "bin.dat": {"content": blob, "encoding": "base64"},
            "text.md": "hello"})])
        s = load_suite(p)
        setup = dict(s.tasks[0].setup)
        self.assertEqual(setup["bin.dat"], b"\x00\x01binary")
        self.assertEqual(setup["text.md"], b"hello")


class ConfigLoading(Base):
    def test_valid_config_defaults(self):
        p = self.make_config(self.make_agent("write-both"))
        c = load_config(p)
        self.assertEqual(c.adapter_type, "shell")
        self.assertEqual(c.caps.task_timeout_s, 120)
        self.assertIsNone(c.caps.token_budget)
        self.assertEqual(c.model["name"], "test-model")

    def test_missing_file_rejected(self):
        with self.assertRaises(SPError) as ctx:
            load_config(self.tmp / "ghost.json")
        self.assertEqual(ctx.exception.code, "missing_input")

    def test_unknown_adapter_type(self):
        p = self.make_config(self.make_agent("write-both"))
        doc = json.loads(p.read_text())
        doc["adapter"]["type"] = "psychic"
        p.write_text(json.dumps(doc))
        with self.assertRaises(SPError) as ctx:
            load_config(p)
        self.assertIn("shell", str(ctx.exception))

    def test_template_missing_required_placeholders(self):
        p = self.make_config(self.make_agent("write-both"))
        doc = json.loads(p.read_text())
        doc["adapter"]["command_template"] = "true"
        p.write_text(json.dumps(doc))
        with self.assertRaises(SPError):
            load_config(p)

    def test_template_unknown_placeholder(self):
        p = self.make_config(self.make_agent("write-both"))
        doc = json.loads(p.read_text())
        doc["adapter"]["command_template"] += " --x {vibes}"
        p.write_text(json.dumps(doc))
        with self.assertRaises(SPError) as ctx:
            load_config(p)
        self.assertIn("vibes", str(ctx.exception))

    def test_token_budget_too_small(self):
        p = self.make_config(self.make_agent("write-both"),
                             caps={"token_budget": 10})
        with self.assertRaises(SPError):
            load_config(p)

    def test_caps_bounds_enforced(self):
        p = self.make_config(self.make_agent("write-both"),
                             caps={"task_timeout_s": 0})
        with self.assertRaises(SPError):
            load_config(p)

    def test_env_bad_key_rejected(self):
        p = self.make_config(self.make_agent("write-both"),
                             env={"BAD KEY": "v"})
        with self.assertRaises(SPError):
            load_config(p)

    def test_model_requires_name(self):
        p = self.make_config(self.make_agent("write-both"))
        doc = json.loads(p.read_text())
        doc["model"] = {"pinned": True}
        p.write_text(json.dumps(doc))
        with self.assertRaises(SPError):
            load_config(p)


if __name__ == "__main__":
    unittest.main()
