"""Dual-arm runner (issue #1): per task, baseline arm then treatment arm,
back-to-back. Emits a delta report or an explicitly labeled aborted report —
never a silent partial (acceptance criterion 1).

Outcome mapping (rule 3 + rule 6, see docs/FORMATS.md "unknown taxonomy"):
    agent spawn failure        -> unknown  agent_exec_error
    agent wall-clock timeout   -> unknown  agent_timeout
    self-reported token budget -> unknown  token_budget_exceeded
    any check errored          -> unknown  check_error:<checks[i]>
    all checks passed          -> pass
    otherwise                  -> fail     checks_failed
    run deadline hit first     -> unknown  run_deadline_exceeded (arms skipped)
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import __version__, delta as delta_mod
from . import provenance
from .adapters import shell
from .checks import ERROR, FAIL, PASS, apply_check
from .errors import SPError
from .provenance import sha256_bytes, sha256_file, sha256_tree, utc_now_iso

SCHEMA = "skillproof.delta-report/0.1"

LIMITS = [
    "n=1 per arm per task: no variance is estimated; deltas smaller than the "
    "noise you would see across repeated runs are not interpretable (issue #3 "
    "adds measured judge/checker variance).",
    "Token counts are self-reported by the agent via "
    ".skillproof/agent_meta.json; arms whose agent does not report show null "
    "and contribute nothing to cost deltas.",
    "Deterministic checks only in v0: no model-based grading, so tasks whose "
    "quality cannot be decided by files/exit codes are out of scope (issue #3).",
    "Per-task paired order is always baseline-then-treatment in suite file "
    "order; order effects are recorded, not randomized away (docs/DESIGN.md ADR-3).",
    "Contamination status of suites is not yet computed (issue #6): treat "
    "uncontaminated claims as unverified.",
    "Side-effect manifests exclude .skillproof/ (the agent self-report "
    "directory) by contract; a snapshot beyond max_workspace_files is flagged "
    "truncated.",
]

_UNKNOWN_WITHOUT_WORKSPACE = {"run_deadline_exceeded", "harness_error"}


class ArmRecord:
    def __init__(self, arm: str, outcome: str, reason_code: Optional[str],
                 checks: List[dict], agent: Dict[str, object],
                 metrics: Dict[str, object], side_effects: Dict[str, object],
                 caps: Dict[str, object], prov: Dict[str, object]):
        self.d = {
            "arm": arm,
            "outcome": outcome,
            "reason_code": reason_code,
            "checks": checks,
            "agent": agent,
            "metrics": metrics,
            "side_effects": side_effects,
            "caps": caps,
            "provenance": prov,
        }

    def to_dict(self) -> Dict[str, object]:
        return self.d


def _deadline_record(arm: str) -> ArmRecord:
    return ArmRecord(
        arm=arm, outcome="unknown", reason_code="run_deadline_exceeded",
        checks=[],
        agent={"exit_code": None, "timed_out": False,
               "exec_error": "run deadline exceeded before this arm started",
               "duration_ms": 0, "skipped": True},
        metrics={"tokens_in": None, "tokens_out": None, "model": None,
                 "reported": False},
        side_effects={"files_added": [], "files_removed": [], "files_modified": [],
                      "agent_workspace_sha256": None, "snapshot_truncated": False,
                      "files_after": {}},
        caps={"task_timeout_s": None, "max_output_bytes": None,
              "token_budget": None, "flags": ["skipped"]},
        prov={"prompt_sha256": None, "prompt_file": None, "workspace": None,
              "post_check_workspace_sha256": None, "skill_sha256": None},
    )


def _snapshot(workspace: Path, caps) -> Tuple[str, Dict[str, str], bool, int]:
    """Pre-check workspace snapshot, excluding the .skillproof/ self-report dir.
    Returns (tree_sha, {relpath: sha} capped, truncated_flag, visible_count)."""
    visible = []
    for p in sorted(workspace.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(workspace).as_posix()
        if rel == ".skillproof" or rel.startswith(".skillproof/"):
            continue
        visible.append((p, rel))
    entries: Dict[str, str] = {}
    truncated = False
    for i, (p, rel) in enumerate(visible):
        if i >= caps.max_workspace_files:
            truncated = True
            break
        entries[rel] = sha256_file(p)
    tree = sha256_tree(workspace, excludes=(".skillproof",))
    return tree["sha256"], entries, truncated, len(visible)


def _run_arm(task, arm: str, suite, config, skill, run_dir: Path,
             caps, deadline: float) -> ArmRecord:
    arm_dir = run_dir / "raw" / task.id / arm
    workspace = arm_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    prompt_file = arm_dir / "prompt.txt"
    try:
        for rel, blob in task.setup:
            target = workspace.joinpath(*(Path(rel).parts))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
        before = {rel: sha256_bytes(blob) for rel, blob in task.setup}

        prompt_text = task.prompt  # byte-identical across arms (ADR-3)
        skill_dir = skill.path if (arm == "treatment" and skill is not None) \
            else arm_dir / "no-skill"
        if arm == "baseline":
            skill_dir.mkdir(parents=True, exist_ok=True)  # empty: no skill

        timeout_s = task.timeout_s or caps.task_timeout_s
        if time.monotonic() > deadline:
            return _deadline_record(arm)

        agent = shell.run_agent(config, workspace, prompt_text, prompt_file,
                                skill_dir, arm, caps, run_dir, suite.path.parent,
                                timeout_s)

        pre_sha, after, truncated, _count = _snapshot(workspace, caps)
        side_effects = {
            "files_added": sorted(set(after) - set(before)),
            "files_removed": sorted(set(before) - set(after)),
            "files_modified": sorted(k for k in set(before) & set(after)
                                     if before[k] != after[k]),
            "agent_workspace_sha256": pre_sha,
            "snapshot_truncated": truncated,
            "files_after": after,
        }

        meta_file = workspace / ".skillproof" / "agent_meta.json"
        if meta_file.is_file():
            shutil.copyfile(meta_file, arm_dir / "agent_meta.json")

        check_results = [apply_check(spec, i, workspace, caps)
                         for i, spec in enumerate(task.checks)]
        check_dicts = [c.to_dict() for c in check_results]

        budget_exceeded = False
        if agent.meta and caps.token_budget is not None:
            tin = agent.meta.get("tokens_in")
            tout = agent.meta.get("tokens_out")
            if isinstance(tin, int) and isinstance(tout, int):
                budget_exceeded = (tin + tout) > caps.token_budget

        first_error = next((c for c in check_dicts if c["outcome"] == ERROR), None)
        if agent.exec_error:
            outcome, reason = "unknown", "agent_exec_error"
        elif agent.timed_out:
            outcome, reason = "unknown", "agent_timeout"
        elif budget_exceeded:
            outcome, reason = "unknown", "token_budget_exceeded"
        elif first_error:
            outcome, reason = "unknown", "check_error:%s" % first_error["id"]
        elif all(c["outcome"] == PASS for c in check_dicts):
            outcome, reason = "pass", None
        else:
            outcome, reason = "fail", "checks_failed"

        meta = agent.meta or {"tokens_in": None, "tokens_out": None,
                              "model": None, "reported": False}
        post_sha = sha256_tree(workspace)["sha256"]
        flags = []
        if truncated:
            flags.append("snapshot_truncated")
        if agent.meta_note:
            flags.append("agent_meta_note: %s" % agent.meta_note)

        return ArmRecord(
            arm=arm, outcome=outcome, reason_code=reason,
            checks=check_dicts,
            agent={"exit_code": agent.exit_code, "timed_out": agent.timed_out,
                   "exec_error": agent.exec_error,
                   "duration_ms": agent.duration_ms,
                   "log_file": "raw/%s/%s/agent.log" % (task.id, arm),
                   "log_sha256": sha256_file(arm_dir / "agent.log")},
            metrics={"tokens_in": meta.get("tokens_in"),
                     "tokens_out": meta.get("tokens_out"),
                     "model": meta.get("model"),
                     "reported": bool(meta.get("reported"))},
            side_effects=side_effects,
            caps={"task_timeout_s": timeout_s,
                  "max_output_bytes": caps.max_output_bytes,
                  "token_budget": caps.token_budget, "flags": flags},
            prov={"prompt_sha256": sha256_bytes(prompt_text.encode("utf-8")),
                  "prompt_file": "raw/%s/%s/prompt.txt" % (task.id, arm),
                  "workspace": "raw/%s/%s/workspace" % (task.id, arm),
                  "post_check_workspace_sha256": post_sha,
                  "skill_sha256": skill.sha256 if (skill and arm == "treatment") else None},
        )
    except Exception as e:  # noqa: BLE001 — one broken arm must not abort evidence
        return ArmRecord(
            arm=arm, outcome="unknown", reason_code="harness_error",
            checks=[],
            agent={"exit_code": None, "timed_out": False,
                   "exec_error": "harness exception: %s: %s" % (type(e).__name__, e),
                   "duration_ms": 0},
            metrics={"tokens_in": None, "tokens_out": None, "model": None,
                     "reported": False},
            side_effects={"files_added": [], "files_removed": [], "files_modified": [],
                          "agent_workspace_sha256": None, "snapshot_truncated": False,
                          "files_after": {}},
            caps={"task_timeout_s": None, "max_output_bytes": None,
                  "token_budget": None, "flags": []},
            prov={"prompt_sha256": None, "prompt_file": None, "workspace": None,
                  "post_check_workspace_sha256": None, "skill_sha256": None},
        )


def _arms_summary(tasks_out: List[dict]) -> Dict[str, dict]:
    summary = {}
    for arm in ("baseline", "treatment"):
        counts = {"pass": 0, "fail": 0, "unknown": 0}
        tokens_in = tokens_out = 0
        reported = 0
        duration_ms = 0
        for t in tasks_out:
            rec = t[arm]
            counts[rec["outcome"]] += 1
            duration_ms += int(rec["agent"].get("duration_ms") or 0)
            m = rec["metrics"]
            if m.get("reported") and isinstance(m.get("tokens_in"), int) \
                    and isinstance(m.get("tokens_out"), int):
                tokens_in += m["tokens_in"]
                tokens_out += m["tokens_out"]
                reported += 1
        summary[arm] = {
            "pass": counts["pass"], "fail": counts["fail"],
            "unknown": counts["unknown"], "tasks_reported_tokens": reported,
            "tokens_in": tokens_in, "tokens_out": tokens_out,
            "duration_ms_total": duration_ms,
        }
    return summary


def run(suite, config, skill, out_root: Path) -> Tuple[dict, int]:
    out_root = Path(out_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    run_id = provenance.make_run_id({
        "suite": suite.sha256, "config": config.sha256,
        "skill": skill.sha256 if skill else None, "harness": __version__,
    })
    run_dir = out_root / run_id
    if run_dir.exists():
        raise SPError("run_dir_exists",
                      "run dir %s already exists — never overwrite evidence; "
                      "re-run in a moment or change inputs" % run_dir)
    (run_dir / "inputs").mkdir(parents=True)
    (run_dir / "raw").mkdir()

    shutil.copyfile(suite.path, run_dir / "inputs" / "suite.json")
    shutil.copyfile(config.path, run_dir / "inputs" / "config.json")
    if skill is not None:
        shutil.copytree(skill.path, run_dir / "inputs" / "skill")

    deadline = time.monotonic() + config.caps.run_timeout_s
    tasks_out: List[dict] = []
    aborted = False
    for task in suite.tasks:
        recs = {}
        for arm in ("baseline", "treatment"):
            if aborted or time.monotonic() > deadline:
                aborted = True
                recs[arm] = _deadline_record(arm)
            else:
                recs[arm] = _run_arm(task, arm, suite, config, skill,
                                     run_dir, config.caps, deadline)
        entry = {
            "task_id": task.id,
            "baseline": recs["baseline"].to_dict(),
            "treatment": recs["treatment"].to_dict(),
        }
        entry.update(delta_mod.compute(entry["baseline"], entry["treatment"]))
        tasks_out.append(entry)

        (run_dir / "raw" / task.id / "baseline").mkdir(parents=True, exist_ok=True)
        (run_dir / "raw" / task.id / "baseline" / "meta.json").write_text(
            json_dump(entry["baseline"]), encoding="utf-8")
        (run_dir / "raw" / task.id / "treatment").mkdir(parents=True, exist_ok=True)
        (run_dir / "raw" / task.id / "treatment" / "meta.json").write_text(
            json_dump(entry["treatment"]), encoding="utf-8")

    run_dict = {
        "schema": SCHEMA,
        "schema_status": "DRAFT — finalized by issue #4; breaking changes bump "
                         "the minor version",
        "run_id": run_id,
        "run_status": "aborted" if aborted else "complete",
        "collected_at": utc_now_iso(),
        "harness": dict({"version": __version__}, **provenance.host_info()),
        "provenance": {
            "suite": {"path": str(suite.path), "name": suite.name,
                      "sha256": suite.sha256, "task_count": len(suite.tasks)},
            "skill": ({"name": skill.name, "path": str(skill.path),
                       "sha256": skill.sha256, "files": skill.file_count}
                      if skill else None),
            "config": {"path": str(config.path), "sha256": config.sha256,
                       "adapter": config.adapter_type, "model": config.model},
            "order": "per-task paired: baseline then treatment, suite file order",
            "staleness": {
                "collected_at": utc_now_iso(),
                "model_pinned": bool(config.model and config.model.get("pinned")),
                "note": "results are pinned to the suite/config/skill hashes in "
                        "this record; re-run before comparing across model, "
                        "harness, or suite versions (G4).",
            },
        },
        "arms_summary": _arms_summary(tasks_out),
        "tasks": tasks_out,
        "limits": LIMITS,
    }

    from . import record
    record.assert_valid(run_dict)

    (run_dir / "run.json").write_text(json_dump(run_dict), encoding="utf-8")
    from . import report
    (run_dir / "REPORT.md").write_text(
        report.render(run_dict), encoding="utf-8", newline="\n")

    exit_code = 1 if aborted else 0
    return run_dict, exit_code


def json_dump(obj) -> str:
    import json
    return json.dumps(obj, indent=2, ensure_ascii=True) + "\n"
