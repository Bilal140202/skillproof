# Evaluation methodology — v0 (DRAFT)

Status: design document. Principles marked *(source)* credit the project whose practice or
failure shaped the rule.

Implementation status: the harness MVP (issue #1) implements rules 2–8 and
the pairing/provenance mechanics of this document; grading and judge-variance
calibration (§3) remain to be built. See docs/DESIGN.md for how each rule
maps to code, and results/README.md for the committed dogfood run.

## 1. What "works" means

A skill "works" for a task suite under a pinned config when, compared to the same
suite without it, it produces a **delta report** that a reader can act on:

- **Outcome quality** — per-task grade against a versioned rubric (not a vibes
  score; see §3), reported as a distribution, never a single average.
- **Token cost** — input + output tokens per task, and per *session* (a skill's
  instructions are paid on every session; its benefit only on tasks in its zone).
- **Wall time** — per task, recorded but never averaged away.
- **Side effects** — files touched beyond the task's expected surface, commands
  run, network calls made.

The unit of measurement is: `(task suite, skill version, agent, model, harness
config) → delta report`. The report is the product. There is no score.

## 2. Hard design rules

1. **Separate regression evals from benchmark evals.** *(LKOS lesson: mixing a
   fast deterministic suite used per-change with a broad periodic suite produced
   evaluations that proved neither.)* Regression evals: small, deterministic,
   cheap, run on every harness change. Benchmark evals: broad, expensive,
   versioned, run on a schedule. Different suites, different docs, never merged.
2. **Commit the losing runs.** *(Chisle: `2026-07-07-verify-rerun.md` documents
   the run where the tool made output 173% worse, root-caused it, and re-validated
   the fix.)* Every benchmark run — win or loss — lands in `results/` with config,
   raw per-task records, and analysis. A loss with a root cause is worth more
   than a win without one.
3. **Three-valued outcomes.** *(Reticle: pass / fail / unknown, where unknown
   means the evidence could not decide — never a quiet pass.)* A task the grader
   cannot decide is recorded as `unknown`, counted, and shown; `unknown` never
   silently aggregates into either side of a delta.
4. **Minimize model-in-the-loop.** *(Reticle: recorded flows replay
   deterministically for a fixed small cost.)* Everything around the graded task
   — setup, fixtures, runner, parsing — is deterministic code. The model is
   invoked only for the task itself and, where unavoidable, for grading (§3).
   Re-runs must not re-pay authoring.
5. **Provenance on every record.** *(LKOS provenance discipline; anti-slop's
   UPSTREAM.md and merge-provenance mechanics.)* Each result record pins: skill
   source repo + commit + SKILL.md hash, agent name/version, model id, harness
   version, date, seed, suite version. A record that cannot answer "exactly what
   was run?" is invalid and the tooling rejects it.
6. **Fail-closed resource bounds.** *(SkillSpector: documented ceilings on
   bundle/parser/ledger size.)* The harness declares ceilings (suite size, token
   budget per task, wall-clock timeout, output parse limits) and treats exceeding
   them as a recorded failure, not a hang.
7. **Publish the limits table next to the results.** *(Reticle's "Limits":
   strong / partial / not-the-tool / can't-see-yet.)* Every published result set
   carries what the methodology cannot see: judge variance bounds, suite
   coverage gaps, contamination status.
8. **Local-first execution.** No cloud service is required to run the harness or
   to reproduce a result. Models are reached through standard local CLIs;
   everything else is local files.

## 3. Grading protocol (to be built — issue #3)

- Rubrics are versioned artifacts with per-criterion weights and worked examples;
  a rubric change is a suite-version change, and old results stay pinned to old
  rubrics.
- Deterministic checks first (files exist, tests pass, output matches spec) —
  a task is only sent to model-based grading when deterministic checks cannot
  decide it.
- Judge variance is *measured, not assumed*: a calibration sample is graded N
  times per published run and the variance is reported next to the deltas
  (limits table, rule 7).
- Grading is blind to the with/without-skill condition wherever mechanically
  possible.

## 4. Known threats to validity (each gets a task before results publish)

| Threat | Mitigation direction |
| --- | --- |
| Suite contamination (suite author == skill author) | G2/issue #6: provenance separation policy + metadata check |
| Judge variance swamping small deltas | §3 calibration sample; report variance; refuse headline deltas below measured noise |
| Small n (task suites are expensive) | Report per-task records; no averages without dispersion; suite growth is a standing issue |
| Prompt-format sensitivity (skill phrasing vs suite phrasing) | Paraphrase variants of tasks; report sensitivity explicitly instead of one lucky phrasing |
| Model drift invalidating old results | G4: version pinning + staleness markers + re-run policy |
| Selection bias in corpus (only skills that look good) | Corpus includes known-weak and known-bad skills as controls (issue #2) |

## 5. What will exist at the end of Phase 1 (issue #1 acceptance)

1. `harness run --suite S --skill K --config C` produces a valid delta report
   (both arms executed, per-task records, provenance complete) or exits non-zero
   with a reason — no partial silent reports.
2. `results/` contains at least one committed losing run with a root-cause note,
   produced by our own dogfooding before any external claim is made.
3. The limits table exists in the same commit as the first published numbers.
4. Every claim in the README traces to a committed result record or is labeled
   as a hypothesis.
