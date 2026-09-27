"""Run-record validation — rule 5 made mechanical: "A record that cannot
answer 'exactly what was run?' is invalid and the tooling rejects it."

validate_run() returns a list of violations (empty = valid); assert_valid()
raises SPError("invalid_run", ...). Both the report and verify commands go
through this gate, so a record missing provenance is rejected by the tooling.
"""

from __future__ import annotations

from typing import List

from .errors import SPError

SCHEMA = "skillproof.delta-report/0.1"
OUTCOMES = {"pass", "fail", "unknown"}
_UNKNOWN_NO_WORKSPACE = {"run_deadline_exceeded", "harness_error"}


def _viol_record(prefix: str, rec: dict) -> List[str]:
    v: List[str] = []
    if not isinstance(rec, dict):
        return ["%s: record is not an object" % prefix]
    for key in ("arm", "outcome", "reason_code", "checks", "agent", "metrics",
                "side_effects", "caps", "provenance"):
        if key not in rec:
            v.append("%s: missing %r" % (prefix, key))
    if rec.get("outcome") not in OUTCOMES:
        v.append("%s: outcome %r not in %s" % (prefix, rec.get("outcome"),
                                               sorted(OUTCOMES)))
    if rec.get("outcome") == "unknown" and not rec.get("reason_code"):
        v.append("%s: unknown outcome without a reason_code" % prefix)
    if not isinstance(rec.get("checks"), list):
        v.append("%s: checks is not a list" % prefix)
    agent = rec.get("agent")
    if not isinstance(agent, dict) or not {"exit_code", "timed_out",
                                           "exec_error", "duration_ms"} <= set(agent):
        v.append("%s: agent record incomplete" % prefix)
    metrics = rec.get("metrics")
    if not isinstance(metrics, dict) or not {"tokens_in", "tokens_out", "model",
                                             "reported"} <= set(metrics):
        v.append("%s: metrics record incomplete" % prefix)
    se = rec.get("side_effects")
    if not isinstance(se, dict) or not {"files_added", "files_removed",
                                        "files_modified",
                                        "agent_workspace_sha256",
                                        "snapshot_truncated",
                                        "files_after"} <= set(se):
        v.append("%s: side_effects record incomplete" % prefix)
    if not isinstance(rec.get("caps"), dict) or \
            not {"task_timeout_s", "max_output_bytes", "token_budget",
                 "flags"} <= set(rec["caps"]):
        v.append("%s: caps record incomplete" % prefix)
    prov = rec.get("provenance")
    if not isinstance(prov, dict):
        v.append("%s: provenance missing (rule 5: record is invalid)" % prefix)
        return v
    for key in ("prompt_sha256", "prompt_file", "workspace",
                "post_check_workspace_sha256", "skill_sha256"):
        if key not in prov:
            v.append("%s: provenance missing %r" % (prefix, key))
    psha = prov.get("prompt_sha256")
    if not (isinstance(psha, str) and len(psha) == 64) and psha is not None:
        v.append("%s: provenance.prompt_sha256 is not a sha256" % prefix)
    if psha is None and rec.get("reason_code") not in _UNKNOWN_NO_WORKSPACE:
        v.append("%s: provenance.prompt_sha256 missing for an executed arm" % prefix)
    post = prov.get("post_check_workspace_sha256")
    if post is None and rec.get("reason_code") not in _UNKNOWN_NO_WORKSPACE:
        v.append("%s: provenance.post_check_workspace_sha256 missing for an "
                 "executed arm" % prefix)
    if prov.get("skill_sha256") is not None and rec.get("arm") != "treatment":
        v.append("%s: skill_sha256 set on a non-treatment arm" % prefix)
    return v


def validate_run(run: dict) -> List[str]:
    v: List[str] = []
    if not isinstance(run, dict):
        return ["run is not an object"]
    if run.get("schema") != SCHEMA:
        v.append("schema must be %r (got %r)" % (SCHEMA, run.get("schema")))
    for key in ("run_id", "run_status", "collected_at", "harness",
                "provenance", "arms_summary", "tasks", "limits"):
        if key not in run:
            v.append("missing top-level %r" % key)
    if run.get("run_status") not in ("complete", "aborted"):
        v.append("run_status must be 'complete' or 'aborted'")
    h = run.get("harness")
    if not isinstance(h, dict) or not {"version", "python", "os"} <= set(h):
        v.append("harness block incomplete (version/python/os required)")
    p = run.get("provenance")
    if not isinstance(p, dict):
        v.append("provenance block missing")
    else:
        suite = p.get("suite")
        if not isinstance(suite, dict) or not {"path", "name", "sha256",
                                               "task_count"} <= set(suite):
            v.append("provenance.suite incomplete")
        elif not (isinstance(suite.get("sha256"), str) and len(suite["sha256"]) == 64):
            v.append("provenance.suite.sha256 is not a sha256")
        cfg = p.get("config")
        if not isinstance(cfg, dict) or not {"path", "sha256", "adapter",
                                             "model"} <= set(cfg):
            v.append("provenance.config incomplete")
        elif not (isinstance(cfg.get("sha256"), str) and len(cfg["sha256"]) == 64):
            v.append("provenance.config.sha256 is not a sha256")
        if "skill" not in p:
            v.append("provenance.skill missing (use null for single-arm runs)")
        if not isinstance(p.get("order"), str):
            v.append("provenance.order missing")
        st = p.get("staleness")
        if not isinstance(st, dict) or "collected_at" not in st:
            v.append("provenance.staleness incomplete (issue #4 / G4)")
    tasks = run.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        v.append("tasks must be a non-empty list")
    else:
        for t in tasks:
            tid = t.get("task_id", "?") if isinstance(t, dict) else "?"
            if not isinstance(t, dict) or "task_id" not in t:
                v.append("task entry missing task_id")
                continue
            for arm in ("baseline", "treatment"):
                if arm not in t:
                    v.append("task %s: arm %r missing (never a silent partial)"
                             % (tid, arm))
                else:
                    v.extend(_viol_record("task %s/%s" % (tid, arm), t[arm]))
            d = t.get("outcome_shift") if isinstance(t, dict) else None
            if d is None:
                v.append("task %s: delta block missing" % tid)
    if isinstance(run.get("limits"), list) is False or not run.get("limits"):
        v.append("limits table missing (rule 7: publish limits next to results)")
    return v


def assert_valid(run: dict) -> None:
    violations = validate_run(run)
    if violations:
        raise SPError("invalid_run",
                      "run record rejected: %d provenance/completeness "
                      "violation(s): %s" % (len(violations), "; ".join(violations[:8])))
