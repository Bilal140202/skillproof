"""verify: recompute every hash a run record claims (tamper-evidence) and
reject records with incomplete provenance (rule 5, acceptance criterion 2).

Exit code 0 = every claim checked out; 1 = at least one problem.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from . import record
from .provenance import sha256_file, sha256_tree


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def verify_run(run_dir: Path) -> Tuple[List[str], int]:
    run_dir = Path(run_dir)
    problems: List[str] = []
    checked = 0

    run_path = run_dir / "run.json"
    if not run_path.is_file():
        return ["run.json not found in %s" % run_dir], 0
    try:
        run = json.loads(run_path.read_text(encoding="utf-8"))
    except Exception as e:
        return ["run.json is not valid JSON: %s" % e], 0

    violations = record.validate_run(run)
    if violations:
        problems.append("record rejected by validator (%d violation(s)): %s"
                        % (len(violations), "; ".join(violations[:6])))

    # 1. inputs: byte-identical copies must still hash to the recorded values
    prov = run.get("provenance", {})
    suite_sha = (prov.get("suite") or {}).get("sha256")
    cfg_sha = (prov.get("config") or {}).get("sha256")
    for name, expected in (("suite.json", suite_sha), ("config.json", cfg_sha)):
        f = run_dir / "inputs" / name
        if expected and f.is_file():
            checked += 1
            got = sha256_file(f)
            if got != expected:
                problems.append("inputs/%s hash drifted: recorded %s..., now %s..."
                                % (name, str(expected)[:12], got[:12]))
        elif expected:
            problems.append("inputs/%s missing (provenance cannot be re-verified)"
                            % name)
    skill = prov.get("skill")
    if isinstance(skill, dict) and skill.get("sha256"):
        d = run_dir / "inputs" / "skill"
        if d.is_dir():
            checked += 1
            got = sha256_tree(d)["sha256"]
            if got != skill["sha256"]:
                problems.append("inputs/skill hash drifted")
        else:
            problems.append("inputs/skill missing")

    # 2. per-arm artifacts: meta.json equality, prompt hash, workspace tree hash
    for t in run.get("tasks", []):
        tid = t.get("task_id", "?")
        for arm in ("baseline", "treatment"):
            rec = t.get(arm)
            if not isinstance(rec, dict):
                continue
            reason = rec.get("reason_code")
            if reason in record._UNKNOWN_NO_WORKSPACE:  # noqa: SLF001 — deliberate
                continue
            arm_dir = run_dir / "raw" / str(tid) / arm
            meta_f = arm_dir / "meta.json"
            if not meta_f.is_file():
                problems.append("task %s/%s: meta.json missing" % (tid, arm))
                continue
            checked += 1
            try:
                stored = json.loads(meta_f.read_text(encoding="utf-8"))
            except Exception as e:
                problems.append("task %s/%s: meta.json unreadable: %s" % (tid, arm, e))
                continue
            if _canon(stored) != _canon(rec):
                problems.append("task %s/%s: meta.json no longer matches run.json "
                                "(records were edited after the run)" % (tid, arm))
            p = rec.get("provenance") or {}
            prompt_f = arm_dir / "prompt.txt"
            if p.get("prompt_sha256") and prompt_f.is_file():
                checked += 1
                if sha256_file(prompt_f) != p["prompt_sha256"]:
                    problems.append("task %s/%s: prompt.txt hash drifted" % (tid, arm))
            ws = arm_dir / "workspace"
            if p.get("post_check_workspace_sha256"):
                if not ws.is_dir():
                    problems.append("task %s/%s: workspace snapshot missing" % (tid, arm))
                else:
                    checked += 1
                    got = sha256_tree(ws)["sha256"]
                    if got != p["post_check_workspace_sha256"]:
                        problems.append(
                            "task %s/%s: workspace hash drifted (post-check "
                            "snapshot no longer matches record)" % (tid, arm))
            se = rec.get("side_effects") or {}
            files_after = se.get("files_after") or {}
            if files_after and ws.is_dir():
                for rel, sha in sorted(files_after.items())[:50]:
                    f = ws / rel
                    if not f.is_file() or sha256_file(f) != sha:
                        problems.append("task %s/%s: workspace file %s drifted"
                                        % (tid, arm, rel))
                        break

    return problems, checked
