# Root cause note — run 20260927T035139Z-5910895f (DOGFOOD, scripted agent)

Scope disclaimer first: this run's agent is **scripted and deterministic**
(`examples/demo_agent.py`, no LLM). It is committed to satisfy EVALUATION.md
rule 2 ("commit the losing runs") and to prove the harness reports losses
mechanically correctly. **It measures plumbing, not skill merit.** No
model-derived claim may cite this run.

## What was lost

- `t004-count-line`: **pass -> fail regression.** Baseline wrote the required
  exact line `Total: 42 items`; the treatment arm followed the skill's rule 4
  ("spell out small numbers: write 'forty-two', never '42'") and wrote
  `Total: forty-two items`, failing the `file_contains` check.

## Root cause

A style rule in the skill (`examples/skills/notes-format-skill/SKILL.md`,
rule 4) is **over-broad relative to the suite**: it rewrites numeric output in
contexts where the task specification demands exact numeric text. This is a
genuine and common failure mode of prescriptive skills — they apply their
conventions unconditionally, and any task whose checker pins exact strings
collides with them. The conflict is intentional in this demo suite: it exists
so the harness's regression semantics (pass -> fail, `regression: true`,
`checks_pass_delta: -1`) are exercised and observed, not assumed.

Lessons carried forward to the corpus work (issue #2) and grading protocol
(issue #3):

1. Suites must declare which checks are *spec-exact* and skills that rewrite
   surface forms will regress against them; corpus tasks should sample both
   (style-flexible and spec-exact) deliberately.
2. A skill whose instructions cannot state their own applicability boundary
   ("apply unless the task pins exact output") is a measurable hazard, and a
   delta report is exactly the instrument that shows it.

## Also recorded in this run (not a loss)

- `t005-summary-brief`: treatment arm reported 27,740 tokens against
  `caps.token_budget: 20000` -> outcome `unknown`
  (`token_budget_exceeded`), by construction. Confirms the fail-closed
  ceiling (rule 6): a budget hit is recorded evidence, never a hang and
  never a silent pass.
- `t001-notes-with-highlights`: fail -> pass improvement (the skill's footer
  compliance), also by construction.

## Harness defect found and fixed by this dogfood cycle

The first committed attempt of this run failed all 10 arms: with a relative
`--out`, the runner passed relative paths into the agent command template,
and the agent subprocess (whose cwd is the workspace) resolved them outside
the workspace. Fixed in `skillproof/adapters/shell.py` (all template values
are now resolved to absolute paths) with regression test
`tests/test_cli.py::test_relative_out_root_resolves_paths`. The defective
run was deleted before anything was claimed from it; this note records that
it happened.
