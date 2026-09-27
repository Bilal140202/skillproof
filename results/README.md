# Results ledger

Every committed run under this directory is a complete, verified delta report
(`run.json` + `REPORT.md` + raw per-arm artifacts + root-cause note when a
run loses). This ledger is the seed of the append-only failure ledger
(issue #5). Nothing here may be deleted or rewritten; new runs append new
rows. `python3 -m skillproof verify --run results/<run_id>` re-checks every
hash in any row.

Honesty labels: each row states its **scope**. `dogfood/scripted` rows use
the deterministic demo agent and measure harness plumbing — they support
zero claims about any real skill's effect on any real model. Model-derived
rows (none yet) will pin suite, skill, config, and model hashes and will be
the only rows citable for effectiveness claims.

| run_id | date (UTC) | suite | skill | headline | scope | notes |
| --- | --- | --- | --- | --- | --- | --- |
| `20260927T035139Z-5910895f` | 2026-09-27 | `release-notes-basics` (5 tasks, `c5eb1fca…`) | `notes-format-skill` (`4e20bf11…`) | baseline 4 pass / 1 fail; treatment 3 pass / 1 fail / 1 unknown; **1 regression (t004 pass->fail)**, 1 improvement (t001 fail->pass), 1 unknown (`token_budget_exceeded`, t005) | dogfood / scripted agent | root cause: skill style rule vs. exact-output spec — see [ROOT_CAUSE.md](20260927T035139Z-5910895f/ROOT_CAUSE.md) |
