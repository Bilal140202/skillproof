"""Per-task paired deltas. Counts and shifts only — no score, by construction
(README non-goals; EVALUATION.md §1)."""

from __future__ import annotations

from typing import Dict, Optional


def _passes(rec: Dict[str, object]) -> int:
    return sum(1 for c in rec["checks"] if c["outcome"] == "pass")


def _tokens(rec: Dict[str, object]) -> Optional[int]:
    m = rec["metrics"]
    if m.get("reported") and isinstance(m.get("tokens_in"), int) \
            and isinstance(m.get("tokens_out"), int):
        return m["tokens_in"] + m["tokens_out"]
    return None


def compute(baseline: Dict[str, object], treatment: Dict[str, object]) -> Dict[str, object]:
    shift = "%s->%s" % (baseline["outcome"], treatment["outcome"])
    checks_delta: Optional[int] = None
    if baseline["checks"] and treatment["checks"]:
        checks_delta = _passes(treatment) - _passes(baseline)
    t_b, t_t = _tokens(baseline), _tokens(treatment)
    tokens_delta = (t_t - t_b) if (t_b is not None and t_t is not None) else None
    d_b = baseline["agent"].get("duration_ms")
    d_t = treatment["agent"].get("duration_ms")
    dur_delta = (d_t - d_b) if (isinstance(d_b, int) and isinstance(d_t, int)) else None
    return {
        "outcome_shift": shift,
        "checks_pass_delta": checks_delta,
        "tokens_delta": tokens_delta,
        "duration_delta_ms": dur_delta,
        "improvement": shift == "fail->pass",
        "regression": shift == "pass->fail",
    }
