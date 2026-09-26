# Gap register

Ordered by priority. Each gap states the evidence that it is open (no existing
tool covers it, per LANDSCAPE.md) and what closing it requires.

## G1 (P0) — Effectiveness evaluation: does a skill improve task outcomes?

**Open because:** SkillSpector covers safety, Chisle covers token cost of
rulesets, Reticle covers app behavior, anti-slop covers static pattern quality —
none measures the delta a skill produces on task outcomes. NVIDIA's "evaluate"
stage is closed-source. No open protocol, harness, or published methodology
exists.

**Closing it requires:** a task-suite runner that executes each task with and
without a candidate skill under a pinned agent/model config; a grading protocol;
a delta report (quality / tokens / time / side effects); provenance for every
run. → issues #1, #2, #3, #4.

## G2 — No shared, contamination-controlled task suites

**Open because:** every tool self-benchmarks on private fixtures (Chisle commits
fixtures; Reticle commits its own harness; SkillSpector's dataset is not
published). Nothing is cross-tool comparable, and suite authorship overlaps with
tool authorship — the incentive problem that makes self-benchmarks untrustworthy.

**Closing it requires:** task suites with explicit provenance separation between
suite author and skill author; a policy statement plus mechanically checkable
metadata. → issue #6.

## G3 — No machine-readable result format for skill evaluations

**Open because:** security scanning standardized early (SARIF 2.1.0 out of
SkillSpector); effectiveness evaluation has no equivalent, so results cannot
accumulate, be diffed over time, or be consumed by registries.

**Closing it requires:** a JSON result schema (run config, skill provenance,
per-task records, aggregate deltas, verdicts with `unknown` states) designed for
diffing and longitudinal storage. → issue #4.

## G4 — No longitudinal re-evaluation (skill decay)

**Open because:** skills encode prompts tuned to particular model generations.
Models and agent harnesses change monthly; nobody re-runs old evaluations, so
published results rot silently. No tool even tracks "this skill's last evaluated
config" over its history.

**Closing it requires:** result records pinned to model/agent/harness versions +
a re-run policy (scheduled or on-version-change) + visible staleness markers on
old results. → issue #4, #5.

## G5 — Interaction effects between skills

**Open because:** skills compose (multiple installed at once, sharing the context
window). Token cost is paid per session; benefits overlap and interfere. No tool
measures pairwise or set-level effects.

**Closing it requires:** the harness from G1 plus factorial run support
(with/without sets of skills) — deliberately deferred until G1 exists; listed now
so the result format does not preclude it.

## G6 — Cost-adjusted verdicts

**Open because:** quality delta and token delta are reported (if at all) by
different tools on different scales. Chisle owns the cost axis alone; nobody joins
"how much better" with "how much more expensive per session".

**Closing it requires:** the delta report to carry both axes in one record with
the session-count assumption stated explicitly, so a reader can apply their own
usage profile. No composite score (see README non-goals).

## Explicitly out of scope (owned elsewhere)

- Maliciousness/vulnerability detection → SkillSpector (SARIF, risk scores).
- Runtime app verification → Reticle (verdicts + `file:line`).
- Output-token compression itself → Chisle (SkillProof would only measure it).
- Skill discovery/distribution → ui-skills, skills.sh.
- Prescribing coding style → anti-slop.
