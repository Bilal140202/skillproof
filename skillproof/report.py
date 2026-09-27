"""Human-readable delta report (REPORT.md). ASCII tables, limits included
in the same document as the numbers (rule 7)."""

from __future__ import annotations

from typing import Dict, List


def _skill_label(run: Dict[str, object]) -> str:
    skill = run["provenance"].get("skill")
    if not skill:
        return "(none)"
    return "%s @ %s" % (skill.get("name"), str(skill.get("sha256"))[:12])


def render(run: Dict[str, object]) -> str:
    prov = run["provenance"]
    suite = prov["suite"]
    lines: List[str] = []
    lines.append("# SkillProof delta report %s" % run["run_id"])
    lines.append("")
    lines.append("- run_status: **%s** (aborted = arms were skipped after the "
                 "run deadline; counts below are still explicit)" % run["run_status"])
    lines.append("- collected_at: %s" % run["collected_at"])
    lines.append("- harness: v%s (python %s, %s)"
                 % (run["harness"]["version"], run["harness"]["python"],
                    run["harness"]["os"]))
    lines.append("- suite: %s (%d tasks, sha256 %s)"
                 % (suite["name"], suite["task_count"], str(suite["sha256"])[:16]))
    lines.append("- skill: %s" % _skill_label(run))
    cfg = prov["config"]
    model = cfg.get("model") or {}
    lines.append("- config: adapter=%s model=%s model_pinned=%s (sha256 %s)"
                 % (cfg["adapter"], model.get("name", "(unspecified)"),
                    model.get("pinned", False), str(cfg["sha256"])[:16]))
    lines.append("- order: %s" % prov["order"])
    lines.append("- staleness: collected_at=%s; re-run before comparing across "
                 "model/harness/suite versions" % prov["staleness"]["collected_at"])
    lines.append("")

    s = run["arms_summary"]
    lines.append("## Arm summary")
    lines.append("")
    lines.append("| arm | pass | fail | unknown | tokens in (reported) | tokens out (reported) | wall ms total |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for arm in ("baseline", "treatment"):
        a = s[arm]
        lines.append("| %s | %d | %d | %d | %d (%d tasks) | %d | %d |"
                     % (arm, a["pass"], a["fail"], a["unknown"],
                        a["tokens_in"], a["tasks_reported_tokens"],
                        a["tokens_out"], a["duration_ms_total"]))
    lines.append("")

    lines.append("## Per-task deltas")
    lines.append("")
    lines.append("| task | baseline | treatment | shift | checks pass delta | tokens delta | duration delta ms |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for t in run["tasks"]:
        d = t
        tok = "n/a" if d["tokens_delta"] is None else ("%+d" % d["tokens_delta"])
        dur = "n/a" if d["duration_delta_ms"] is None else ("%+d" % d["duration_delta_ms"])
        cpd = "n/a" if d["checks_pass_delta"] is None else ("%+d" % d["checks_pass_delta"])
        lines.append("| %s | %s | %s | %s | %s | %s | %s |"
                     % (t["task_id"], t["baseline"]["outcome"],
                        t["treatment"]["outcome"], d["outcome_shift"],
                        cpd, tok, dur))
    lines.append("")

    regressions = [t for t in run["tasks"] if t["regression"]]
    improvements = [t for t in run["tasks"] if t["improvement"]]
    unknowns = [(t[arm], t["task_id"], arm)
                for t in run["tasks"] for arm in ("baseline", "treatment")
                if t[arm]["outcome"] == "unknown"]

    lines.append("## What changed")
    lines.append("")
    lines.append("- improvements (fail->pass): %s"
                 % (", ".join(t["task_id"] for t in improvements) or "(none)"))
    lines.append("- regressions (pass->fail): %s"
                 % (", ".join(t["task_id"] for t in regressions) or "(none)"))
    if unknowns:
        lines.append("- unknowns: %s"
                     % ", ".join("%s/%s (%s)" % (tid, arm, rec["reason_code"])
                                 for rec, tid, arm in unknowns))
    lines.append("")
    lines.append("A delta is a measurement, not a verdict: read the per-task "
                 "records and the limits below before deciding anything.")
    lines.append("")

    lines.append("## Unknown reason codes present")
    lines.append("")
    if unknowns:
        seen = sorted({t["reason_code"] for t, _i, _a in unknowns})
        for code in seen:
            lines.append("- `%s`" % code)
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## Limits (rule 7: published next to the numbers)")
    lines.append("")
    for lim in run["limits"]:
        lines.append("- %s" % lim)
    lines.append("")

    lines.append("## Artifacts")
    lines.append("")
    lines.append("- `run.json` — this report's machine-readable source "
                 "(schema %s, %s)" % (run["schema"], run.get("schema_status", "")))
    lines.append("- `inputs/` — byte-identical copies of suite, config, skill")
    lines.append("- `raw/<task>/<arm>/` — prompt.txt, agent.log, meta.json, "
                 "workspace/ snapshot")
    lines.append("- Re-grade without re-run: `raw/` keeps everything grading "
                 "needs (EVALUATION.md rule 4).")
    lines.append("")
    return "\n".join(lines)
