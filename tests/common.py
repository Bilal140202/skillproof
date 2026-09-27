"""Shared helpers: build suites/configs/skills/agents in tmp dirs and run the
harness end-to-end through the real loaders (no mocks on the hot path)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from skillproof.config import Caps, load_config
from skillproof.skillbundle import load_skill
from skillproof.suite import load_suite

AGENT_TEMPLATE = '''\
import argparse, json, pathlib, sys, time
ap = argparse.ArgumentParser()
ap.add_argument("--workspace"); ap.add_argument("--prompt-file")
ap.add_argument("--skill-dir"); ap.add_argument("--arm")
a = ap.parse_args()
ws = pathlib.Path(a.workspace)
(ws / ".skillproof").mkdir(parents=True, exist_ok=True)
mode = %(mode)r
prompt = pathlib.Path(a.prompt_file).read_text()
if mode == "write-on-skill":
    (ws / "out.txt").write_text(
        "done-with-skill" if a.arm == "treatment" else "done-baseline")
elif mode == "write-both":
    (ws / "out.txt").write_text("done")
elif mode == "sleep":
    time.sleep(3)
elif mode == "crash":
    sys.exit(3)
elif mode == "exit-nonzero-but-write":
    (ws / "out.txt").write_text("done-with-skill")
    sys.exit(1)
elif mode == "over-budget":
    (ws / "out.txt").write_text("done")
elif mode == "overwrite-setup":
    (ws / "seed.txt").write_text("changed")
    gone = ws / "gone.txt"
    if gone.exists():
        gone.unlink()
elif mode == "bad-meta":
    (ws / ".skillproof" / "agent_meta.json").write_text("{not json")
elif mode == "silent":
    pass
if mode != "bad-meta":
    meta = {"tokens_in": 100, "tokens_out": 20, "model": "test-agent"}
    if mode == "over-budget" and a.arm == "treatment":
        meta = {"tokens_in": 50000, "tokens_out": 5000, "model": "test-agent"}
    (ws / ".skillproof" / "agent_meta.json").write_text(json.dumps(meta))
'''

SKILL_MD = """---
name: test-skill
description: used by harness tests
---
# Test skill

Do the task exactly as the prompt says.
"""

BASE_CAPS = Caps(task_timeout_s=10, run_timeout_s=60, max_output_bytes=65_536,
                 token_budget=None, max_workspace_files=2000, max_file_bytes=1_000_000)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    # --- builders ----------------------------------------------------------

    def make_agent(self, mode: str) -> Path:
        p = self.tmp / "agent.py"
        p.write_text(AGENT_TEMPLATE % {"mode": mode}, encoding="utf-8")
        return p

    def make_skill(self) -> Path:
        d = self.tmp / "skill"
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
        return d

    def make_suite(self, tasks, name="test-suite") -> Path:
        doc = {"schema": "skillproof.suite/0.1", "name": name, "tasks": tasks}
        p = self.tmp / "suite.json"
        p.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return p

    def make_config(self, agent_path: Path, env=None, caps=None) -> Path:
        doc = {
            "schema": "skillproof.config/0.1",
            "adapter": {
                "type": "shell",
                "command_template": "%s %s --workspace {workspace} "
                                    "--prompt-file {prompt_file} "
                                    "--skill-dir {skill_dir} --arm {arm}"
                                    % (sys.executable, agent_path),
                "env": env or {},
            },
            "model": {"name": "test-model", "pinned": True},
        }
        if caps:
            doc["caps"] = caps
        p = self.tmp / "config.json"
        p.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return p

    def default_task(self, **over):
        task = {
            "id": "t001",
            "prompt": "produce out.txt containing done-with-skill",
            "checks": [{"type": "file_contains", "path": "out.txt",
                        "text": "done-with-skill"}],
        }
        task.update(over)
        return task

    def load_and_run(self, mode="write-on-skill", tasks=None, env=None,
                     caps=None, out="results"):
        suite_p = self.make_suite(tasks if tasks is not None else [self.default_task()])
        config_p = self.make_config(self.make_agent(mode), env=env, caps=caps)
        skill = load_skill(self.make_skill())
        from skillproof import runner
        run_dict, exit_code = runner.run(load_suite(suite_p), load_config(config_p),
                                         skill, self.tmp / out)
        return run_dict, exit_code, self.tmp / out / run_dict["run_id"]
