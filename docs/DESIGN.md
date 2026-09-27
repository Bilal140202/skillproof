# Design decisions — harness v0

Each ADR states the decision, the reasoning, and what we consciously gave up.
Rule numbers refer to EVALUATION.md §2.

## ADR-1: Python 3.9+, standard library only

Zero runtime dependencies (the Chisle precedent, applied to an eval harness).
An evaluator that measures trust should itself be auditable end to end: every
line that touches evidence is readable without a dependency audit, and the
supply-chain surface is the CPython stdlib. Consequences we accept: JSON
instead of YAML for suites/configs; hand-rolled strict validation instead of
pydantic; no rich progress UI. An eval harness that needs `pip install` to
re-run last quarter's numbers is a reproducibility hazard, not a convenience
gap.

## ADR-2: exactly one agent adapter — `shell`

The harness drives any local CLI agent through a command template
(`{workspace}`, `{prompt_file}`, `{skill_dir}`, `{arm}`; argv-split, no
shell). This keeps rule 8 (local-first) literally true and keeps the
model-in-the-loop surface at exactly one subprocess call (rule 4). API-backed
adapters (OpenAI-compatible endpoints, vendor SDKs) are deliberately absent
in v0: they would add credentials, network flakiness, and unpinned
server-side drift into the measurement path before the local pipeline is
proven. A real agent costs nothing to add: point `command_template` at it.

## ADR-3: per-task paired arms, baseline immediately before treatment

For each task the baseline arm runs, then the treatment arm, then checks —
paired at task granularity in suite file order. The prompt is byte-identical
across arms (hash recorded twice per record and asserted equal by tests); the
only differences are `--skill-dir` (empty dir for baseline) and
`SKILLPROOF_ARM`. Blocked ordering (all baselines, then all treatments) was
rejected: back-to-back pairing minimizes within-pair drift for long suites.
Order effects across pairs are *recorded, not randomized away* — that is a
listed limit (rule 7), and a candidate randomization extension for v0.1.

## ADR-4: unknown taxonomy is exhaustive and mechanical

Every non-{pass,fail} path maps to a named reason code (docs/FORMATS.md §4).
Design invariant: a ceiling hit, a crashed checker, or an unstartable agent
can never degrade into `fail` (which would blame the skill) or `pass` (which
would credit it). The validator (skillproof/record.py) rejects records where
`unknown` lacks a reason code or an executed arm lacks workspace/prompt
hashes — rule 5 ("the tooling rejects it") is code, not policy.

## ADR-5: two workspace hashes per arm, by design

`agent_workspace_sha256` (pre-check, excludes `.skillproof/`) measures the
*agent's* side effects; `post_check_workspace_sha256` (whole tree, taken
after checks) is what `verify` recomputes later. Splitting them means checks
that build artifacts (test runners writing `__pycache__/`) do not corrupt the
agent-attribution manifest, and committed runs remain bit-verifiable years
later. Snapshot listing (`files_after`) is capped at `max_workspace_files`
with a truncation flag; the tree hash always covers everything.

## ADR-6: no score, by construction

There is no aggregate quality number in the schema — not in `arms_summary`,
not in the report. Counts, shifts, and per-axis deltas only (README
non-goals). The cheapest way to resist "just give me the one number" pressure
is for the number to not exist.

## ADR-7: evidence directories are never overwritten or ignored

`results/<run_id>/` collision is a hard error (`run_dir_exists`), the
gitignore deliberately does not exclude `results/` or `*.log`, and `verify`
treats post-hoc edits as failures. This operationalizes rule 2 (commit the
losing runs) — a ledger that silently overwrites or ignores run artifacts is
not a ledger.

## Known limitations of harness v0 (each mapped to future work)

- Token counts are self-reported; agents that do not write
  `.skillproof/agent_meta.json` produce null cost axes. (Format extension:
  adapter-level accounting when API adapters land.)
- Deterministic checks only; no model-based grading, no judge-variance
  calibration. (issue #3)
- Suite contamination is not computed. (issue #6)
- Result format is DRAFT. (issue #4)
- No paraphrase-variant expansion of prompts. (issue #2 corpus work)
- Windows is untested (tests use POSIX `sh` in command checks); the CI
  matrix covers Linux 3.9/3.12 and macOS 3.12.
