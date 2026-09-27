# SkillProof

**Does an agent skill actually work? Almost nobody measures that.**

The agent-skills ecosystem already has serious tooling around the skill as a unit of
distribution: install-time security scanning, runtime verification of what agents
build, token-efficiency rulesets, curated registries, and static quality linting.
Each answers one question *around* a skill:

| Question | Answered today by |
| --- | --- |
| Is this skill safe to install? | [SkillSpector](https://github.com/NVIDIA/SkillSpector) (NVIDIA) |
| Does the code it helped produce actually work? | [Reticle](https://github.com/reticlehq/reticle) |
| Does it waste tokens and inflate output? | [Chisle](https://github.com/JayPokale/Chisle) |
| Where do I find good skills? | [ui-skills](https://github.com/ibelick/ui-skills) |
| Does it encode low-evidence code patterns? | [anti-slop](https://github.com/dmmulroy/anti-slop) |
| **Does installing it measurably improve agent performance on real tasks — and at what cost?** | **nobody (open)** |

SkillProof is an evidence-first evaluation lab for that last question.

The core measurement is a **delta report**: same task suite, same agent config,
with and without a candidate skill — outcome quality, token cost, wall time, and
side effects, with provenance for every number and the losing runs published
alongside the winning ones.

## Quickstart (fully offline)

```sh
git clone https://github.com/Bilal140202/skillproof && cd skillproof
./bin/harness demo                 # scripted agent, 5 tasks, ~10 seconds
./bin/harness verify --run "$(ls -d skillproof-demo/results/*)"
```

The demo produces a real delta report containing all four outcome shapes:
an improvement (fail->pass), neutrals, a regression (pass->fail), and an
unknown (token budget exceeded). Against a real agent, the same command shape
applies — point the config's `command_template` at your local CLI:

```sh
./bin/harness run --suite my-suite.json --skill path/to/skill --config my-config.json
```

Formats: [docs/FORMATS.md](docs/FORMATS.md) · Design decisions:
[docs/DESIGN.md](docs/DESIGN.md) · Methodology: [EVALUATION.md](EVALUATION.md).
No dependencies beyond Python 3.9+; nothing to install.

## Status — honest maturity labels

No number on this page is a model-derived measurement. Phase 0 (research
foundation) is done; Phase 1 (instrumentation) has started with the harness
MVP. The harness is real and tested; the measurements it will be trusted for
(model-in-the-loop runs on the issue #2 corpus) do not exist yet.

| Component | Status | Evidence |
| --- | --- | --- |
| Landscape analysis — 5 adjacent tools, code-verified | **REAL** | [LANDSCAPE.md](LANDSCAPE.md) — every claim checked against cloned sources at pinned commits |
| Gap register | **REAL** | [GAPS.md](GAPS.md) |
| Evaluation methodology | **DRAFT** | [EVALUATION.md](EVALUATION.md) — v0 in effect for the harness below |
| Evaluation harness | **REAL (MVP)** | runnable: `bin/harness run` emits provenance-complete delta reports with three-valued outcomes and fail-closed ceilings; 77 stdlib-only tests; `verify` recomputes every recorded hash; committed dogfood run with a regression + root cause under [results/](results/README.md). Not yet: API adapters, model-based grading (issue #3) |
| Skill corpus + task suites | **MISSING** | issue #2 |
| Grading protocol (rubrics, judge variance) | **MISSING** | issue #3 |
| Machine-readable result format + provenance | **DRAFT** | [docs/FORMATS.md](docs/FORMATS.md) — implemented in the harness, finalized by issue #4 |
| Published results (wins *and* losses) | **DOGFOOD ONLY** | one scripted-agent run committed under [results/](results/README.md) — it exercises the plumbing and is labeled as such; zero model-derived claims exist |

## Non-goals

- **Not a security scanner.** That is SkillSpector's lane, and it is good at it.
  SkillProof consumes safety verdicts as an input, it does not produce them.
- **Not a runtime app verifier.** That is Reticle's lane. When a skill's effect is
  visible in a running app, Reticle is the evidence source, not SkillProof.
- **Not a registry or marketplace.** Distribution is solved (ui-skills, skills.sh).
- **Not a coding-style ruleset.** anti-slop owns that; SkillProof would *measure*
  whether such rulesets help, not prescribe one.
- **No single "skill score".** A skill that cuts tokens 40% but breaks edge cases
  is not "0.7 good". Multi-dimensional reports only, decisions left to the reader.

## Working hypotheses (to be tested, not asserted)

1. Skill effects are task-dependent enough that any single-number rating misleads.
2. Token cost of a skill is paid on every session; its benefit is paid only on
   tasks in its zone — so cost-adjusted effectiveness is the honest headline.
3. Skills decay as models change; without re-running evaluations periodically,
   published results rot silently. Evaluation must be re-runnable by design.

## The five references

Studied at code level (cloned sources, pinned commits — see LANDSCAPE.md for what
was verified rather than trusted from READMEs):

| Repo | Verified at | What it is, from its own source tree |
| --- | --- | --- |
| [NVIDIA/SkillSpector](https://github.com/NVIDIA/SkillSpector) | `89e9087` | LangGraph scan pipeline → SARIF 2.1.0 + risk score; 33 analyzer modules |
| [reticlehq/reticle](https://github.com/reticlehq/reticle) | `d855606` | In-app verification: verdicts (pass/fail/unknown) with `file:line` evidence; deterministic flow replay |
| [JayPokale/Chisle](https://github.com/JayPokale/Chisle) | `deac5e4` | Zero-dep ruleset injector for 11 agents; commits 139 benchmark result files including documented failures |
| [ibelick/ui-skills](https://github.com/ibelick/ui-skills) | `f9515cb` | 7 design-engineering skills as `SKILL.md` bundles + CLI + MCP registry |
| [dmmulroy/anti-slop](https://github.com/dmmulroy/anti-slop) | `c44ef22` | 18 Oxlint rules + paired tests, vendored with provenance; installed via a skill that three-way merges |

## License

MIT — see [LICENSE](LICENSE).
