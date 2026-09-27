"""CLI: run / report / verify / demo / version.

EVALUATION.md §5 interface: ``harness run --suite S --skill K --config C``
(``bin/harness`` is a shim for exactly this; ``python3 -m skillproof`` is
the same thing).
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import __version__, runner
from .config import load_config
from .errors import SPError
from .skillbundle import load_skill
from .suite import load_suite


def _print_summary(run_dict, run_dir) -> None:
    s = run_dict["arms_summary"]
    print("run %s [%s]" % (run_dict["run_id"], run_dict["run_status"]))
    print("arm summary: baseline pass=%d fail=%d unknown=%d | "
          "treatment pass=%d fail=%d unknown=%d"
          % (s["baseline"]["pass"], s["baseline"]["fail"], s["baseline"]["unknown"],
             s["treatment"]["pass"], s["treatment"]["fail"], s["treatment"]["unknown"]))
    improvements = [t["task_id"] for t in run_dict["tasks"] if t["improvement"]]
    regressions = [t["task_id"] for t in run_dict["tasks"] if t["regression"]]
    unknowns = ["%s/%s (%s)" % (t["task_id"], arm, t[arm]["reason_code"])
                for t in run_dict["tasks"] for arm in ("baseline", "treatment")
                if t[arm]["outcome"] == "unknown"]
    print("improvements (fail->pass): %s" % (", ".join(improvements) or "(none)"))
    print("regressions (pass->fail): %s" % (", ".join(regressions) or "(none)"))
    if unknowns:
        print("unknowns: %s" % ", ".join(unknowns))
    print("report: %s" % (run_dir / "REPORT.md"))
    print("record: %s" % (run_dir / "run.json"))


def _cmd_run(args) -> int:
    from pathlib import Path
    suite = load_suite(args.suite)
    config = load_config(args.config)
    skill = load_skill(args.skill)
    out_root = Path(args.out)
    print("suite %r (%d tasks, %s)" % (suite.name, len(suite.tasks), suite.sha256[:12]))
    print("skill %r (%s)" % (skill.name, skill.sha256[:12]))
    print("config %s (adapter=%s, caps: task_timeout_s=%d, token_budget=%s)"
          % (config.sha256[:12], config.adapter_type, config.caps.task_timeout_s,
             config.caps.token_budget))
    run_dict, exit_code = runner.run(suite, config, skill, out_root)
    print("")
    _print_summary(run_dict, out_root / run_dict["run_id"])
    if run_dict["run_status"] == "aborted":
        print("WARNING: run aborted at the deadline — report is explicitly "
              "labeled, exit code is non-zero (no silent partials).",
              file=sys.stderr)
    return exit_code


def _cmd_report(args) -> int:
    from pathlib import Path
    from . import report, record
    import json
    run_dir = Path(args.run)
    run_path = run_dir / "run.json"
    if not run_path.is_file():
        raise SPError("missing_input", "run.json not found under %s" % run_dir)
    run_dict = json.loads(run_path.read_text(encoding="utf-8"))
    record.assert_valid(run_dict)
    out = run_dir / "REPORT.md"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(report.render(run_dict))
    print("rewrote %s" % out)
    return 0


def _cmd_verify(args) -> int:
    from pathlib import Path
    from .verify import verify_run
    problems, checked = verify_run(Path(args.run))
    print("verify %s: %d claim(s) recomputed" % (args.run, checked))
    if problems:
        for p in problems:
            print("PROBLEM: %s" % p, file=sys.stderr)
        print("verify FAILED (%d problem(s))" % len(problems), file=sys.stderr)
        return 1
    print("verify OK — all recorded hashes and records check out")
    return 0


def _cmd_demo(args) -> int:
    from .demo import run_demo
    return run_demo(args.out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillproof",
        description="SkillProof harness — dual-arm skill effectiveness "
                    "measurement. No score, deltas only.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser(
        "run", help="run a task suite with and without a skill, emit a delta report")
    p_run.add_argument("--suite", required=True, help="suite JSON (skillproof.suite/0.1)")
    p_run.add_argument("--config", required=True,
                       help="harness config JSON (skillproof.config/0.1)")
    p_run.add_argument("--skill", required=True,
                       help="skill directory containing SKILL.md")
    p_run.add_argument("--out", default="results", help="output root (default: results)")
    p_run.set_defaults(func=_cmd_run)

    p_rep = sub.add_parser("report", help="re-render REPORT.md from a run record")
    p_rep.add_argument("--run", required=True, help="run directory")
    p_rep.set_defaults(func=_cmd_report)

    p_ver = sub.add_parser("verify", help="recompute all hashes/records of a run")
    p_ver.add_argument("--run", required=True, help="run directory")
    p_ver.set_defaults(func=_cmd_verify)

    p_demo = sub.add_parser(
        "demo", help="offline end-to-end demo with a scripted deterministic agent")
    p_demo.add_argument("--out", default="skillproof-demo", help="demo output root")
    p_demo.set_defaults(func=_cmd_demo)

    sub.add_parser("version", help="print harness version")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "version":
        print("skillproof harness %s" % __version__)
        return 0
    try:
        return args.func(args)
    except SPError as e:
        print("error [%s]: %s" % (e.code, e), file=sys.stderr)
        return 2
