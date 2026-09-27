"""Offline demo: copies examples/ into <out>/demo, runs the dual-arm harness
with a scripted deterministic agent, prints the summary.

Honesty note printed at the end: the demo agent is scripted — it exercises
harness plumbing and report semantics, NOT model behavior. See the committed
dogfood run under results/ for the same distinction in writing.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .cli import _print_summary
from .config import load_config
from .errors import SPError
from .runner import run as run_harness
from .skillbundle import load_skill
from .suite import load_suite


def _examples_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "examples"


def run_demo(out_dir) -> int:
    out = Path(out_dir)
    demo_dir = out / "demo"
    results_dir = out / "results"
    if demo_dir.exists():
        shutil.rmtree(demo_dir)
    demo_dir.mkdir(parents=True)

    examples = _examples_dir()
    shutil.copyfile(examples / "suite.example.json", demo_dir / "suite.json")
    shutil.copyfile(examples / "config.example.json", demo_dir / "config.json")
    shutil.copyfile(examples / "demo_agent.py", demo_dir / "demo_agent.py")
    shutil.copytree(examples / "skills" / "notes-format-skill",
                    demo_dir / "skills" / "notes-format-skill")

    suite = load_suite(demo_dir / "suite.json")
    config = load_config(demo_dir / "config.json")
    skill = load_skill(demo_dir / "skills" / "notes-format-skill")

    print("SkillProof offline demo — scripted deterministic agent (no LLM)")
    print("suite %r (%d tasks) | skill %r | config %s"
          % (suite.name, len(suite.tasks), skill.name, config.sha256[:12]))
    print("")
    run_dict, exit_code = run_harness(suite, config, skill, results_dir)
    print("")
    _print_summary(run_dict, results_dir / run_dict["run_id"])
    print("")
    print("What this demonstrates:")
    print("- one command ran BOTH arms per task and produced a delta report")
    print("- t001 is an improvement (fail->pass), t004 a regression (pass->fail),")
    print("  t005 an unknown (token_budget_exceeded): all three are first-class")
    print("- every number carries provenance; verify it:")
    print("    python3 -m skillproof verify --run %s" % (results_dir / run_dict["run_id"]))
    print("Note: the demo agent is scripted; this run measures harness plumbing,")
    print("not model behavior. Committed dogfood run lives in results/ with a")
    print("root-cause note (EVALUATION.md rule 2).")
    return 0
