# SkillProof delta report 20260927T035139Z-5910895f

- run_status: **complete** (aborted = arms were skipped after the run deadline; counts below are still explicit)
- collected_at: 2026-09-27T03:51:39Z
- harness: v0.1.0 (python 3.12.14, Linux-5.10.134-013.15.kangaroo.al8.x86_64-x86_64-with-glibc2.41)
- suite: release-notes-basics (5 tasks, sha256 c5eb1fcac5253afc)
- skill: notes-format-skill @ 4e20bf117fc1
- config: adapter=shell model=scripted-demo-v0 (no LLM) model_pinned=True (sha256 06a03c9d55e32c7f)
- order: per-task paired: baseline then treatment, suite file order
- staleness: collected_at=2026-09-27T03:51:39Z; re-run before comparing across model/harness/suite versions

## Arm summary

| arm | pass | fail | unknown | tokens in (reported) | tokens out (reported) | wall ms total |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 4 | 1 | 0 | 222 (5 tasks) | 200 | 176 |
| treatment | 3 | 1 | 1 | 36722 (5 tasks) | 1400 | 169 |

## Per-task deltas

| task | baseline | treatment | shift | checks pass delta | tokens delta | duration delta ms |
| --- | --- | --- | --- | --- | --- | --- |
| t001-notes-with-highlights | fail | pass | fail->pass | +1 | +2500 | -8 |
| t002-fixes-section | pass | pass | pass->pass | +0 | +2500 | +6 |
| t003-stats-json | pass | pass | pass->pass | +0 | +2500 | -4 |
| t004-count-line | pass | fail | pass->fail | -1 | +2500 | +0 |
| t005-summary-brief | pass | unknown | pass->unknown | +0 | +27700 | -1 |

## What changed

- improvements (fail->pass): t001-notes-with-highlights
- regressions (pass->fail): t004-count-line
- unknowns: t005-summary-brief/treatment (token_budget_exceeded)

A delta is a measurement, not a verdict: read the per-task records and the limits below before deciding anything.

## Unknown reason codes present

- `token_budget_exceeded`

## Limits (rule 7: published next to the numbers)

- n=1 per arm per task: no variance is estimated; deltas smaller than the noise you would see across repeated runs are not interpretable (issue #3 adds measured judge/checker variance).
- Token counts are self-reported by the agent via .skillproof/agent_meta.json; arms whose agent does not report show null and contribute nothing to cost deltas.
- Deterministic checks only in v0: no model-based grading, so tasks whose quality cannot be decided by files/exit codes are out of scope (issue #3).
- Per-task paired order is always baseline-then-treatment in suite file order; order effects are recorded, not randomized away (docs/DESIGN.md ADR-3).
- Contamination status of suites is not yet computed (issue #6): treat uncontaminated claims as unverified.
- Side-effect manifests exclude .skillproof/ (the agent self-report directory) by contract; a snapshot beyond max_workspace_files is flagged truncated.

## Artifacts

- `run.json` — this report's machine-readable source (schema skillproof.delta-report/0.1, DRAFT — finalized by issue #4; breaking changes bump the minor version)
- `inputs/` — byte-identical copies of suite, config, skill
- `raw/<task>/<arm>/` — prompt.txt, agent.log, meta.json, workspace/ snapshot
- Re-grade without re-run: `raw/` keeps everything grading needs (EVALUATION.md rule 4).
