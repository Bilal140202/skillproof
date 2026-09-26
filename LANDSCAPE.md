# Landscape — five adjacent tools, verified at source level

Method: each repository was cloned (shallow) and inspected at the pinned commit
below. Facts cited here come from the source tree, not from README claims, except
where a claim is explicitly marked **[README claim]**. Inspection date: 2026-09-27.

| Repo | Pinned commit | Scale | Language | License |
| --- | --- | --- | --- | --- |
| NVIDIA/SkillSpector | `89e9087` | 391 files (265 `.py`) | Python 3.12+ | Apache-2.0 |
| reticlehq/reticle | `d855606` | 3,087 files (2,312 `.ts`) | TypeScript | Apache-2.0 + FSL (server) |
| JayPokale/Chisle | `deac5e4` | 730 files (557 `.json`, 45 `.js`) | JavaScript (zero deps) | MIT |
| ibelick/ui-skills | `f9515cb` | 256 files (72 `.ts`, 67 `.tsx`, 45 `.astro`) | TypeScript/Astro | MIT |
| dmmulroy/anti-slop | `c44ef22` | 113 files (96 `.ts`) | TypeScript (Oxlint plugin) | MIT |

---

## 1. SkillSpector (NVIDIA) — install-time security scanning

**What the source tree shows.** A LangGraph workflow (`resolve_input → context →
parallel analyzers → meta_analyzer → report`) producing SARIF 2.1.0 reports plus a
risk score, runnable via CLI (`skillspector scan <path|git-url|zip|md>`),
LangGraph Studio, or programmatic invoke; `--no-llm` runs the static pipeline only.

- **33 analyzer modules** in `src/skillspector/nodes/analyzers/`, in four families:
  - *static patterns* (15): prompt injection, data exfiltration, memory poisoning,
    supply chain, privilege escalation, anti-refusal, rogue agent, system prompt
    leakage, output handling, tool misuse, deserialization, excessive agency,
    harmful content, agent snooping, SSRF;
  - *behavioral*: AST analysis + taint tracking;
  - *semantic (LLM-backed)*: developer intent, quality policy, security discovery
    (gated behind `use_llm`, with a model registry);
  - *MCP-specific*: rug pull, tool poisoning, least privilege — plus an OSV
    (vulnerability feed) client, artifact integrity, and whitespace-padding
    evasion detection.
- Tests mirror analyzers: 48 analyzer test modules.
- Fail-closed resource bounds are a documented design axis
  (`docs/ANALYSIS_RESOURCE_BOUNDS.md`).
- **[README claim]** In a 31,132-skill analyzed subset, 26.1% contain
  vulnerabilities and 5.2% show likely malicious intent. The dataset is not in the
  repo, so this is reported as their claim, not verified here.
- Part of NVIDIA's "Verified Skills" pipeline: scan → evaluate → sign → publish.
  **The "evaluate" stage (does the skill work?) is not open-sourced.** That closed
  stage is the closest thing to this project's mission in the ecosystem.

**What SkillProof takes from it:** fail-closed resource bounds; SARIF-style
machine-readable findings; the discipline of separating static/cheap passes from
semantic/expensive passes; risk scoring as a *reported* dimension, not a verdict.

## 2. Reticle — runtime verification of what agents build

**What the source tree shows.** A TypeScript monorepo (server + SDK + adapters)
distributed as an MCP server wired into ~15 coding agents. The core model:
structured predicates over *in-app* signals (network, store/state, console,
signals, element presence) evaluated against a running app, returning
**pass / fail / unknown** with evidence and a `file:line` pointer.

- Verdicts are three-valued *by design*: `unknown` means the evidence could not
  decide — never a quiet pass (their own "Limits" section enumerates what it
  cannot see yet: IndexedDB, Web Workers, closed shadow roots, cross-origin
  iframes).
- Flows can be recorded once and replayed deterministically with no model in the
  loop — re-verification cost drops to a fixed small read.
  **[README claim]** 47 tokens per replay vs ~120k to re-drive with an LLM; 85/86
  injected regressions caught vs 59/86 for a Playwright script. Harness is
  committed (`bench/`, `pnpm bench`).
- Ships itself as a `SKILL.md` (`SKILL.md` at repo root) — evidence that SKILL.md
  has become a distribution interface even for dev tools.
- Governance/roadmap/security docs committed; install is inspectable
  (`--dry-run` before writes).

**What SkillProof takes from it:** the three-valued verdict discipline
(`unknown` as a first-class outcome); recorded replay to minimize model-in-the-loop
cost; publishing a "what this tool cannot see" table next to the benchmark.

## 3. Chisle — token-efficiency rulesets, failures published

**What the source tree shows.** A zero-dependency JS installer that detects the
present coding agents (claims 11; config JSONs in-tree) and injects a ruleset
per agent. Compression acts on three axes: output prose, output code (YAGNI
ladder), and tool-output context (scrub → elide → dedup on `PostToolUse` /
`tool_result`), while explicitly exempting Read/Edit/Write bytes.

- **139 benchmark result files committed** under `benchmarks/results/`, including
  an investigation of its own worst day: `2026-07-07-verify-rerun.md` documents
  the run where Chisle made the model *more* verbose (173% of baseline), the root
  cause in the ruleset, and the live re-validation after the fix (93%).
  **[README claim]** 44% output-token reduction vs bare model; specialist tools
  in the same class blow up to 424% of baseline on their worst task.
- Fixtures for agentic benchmarks are in-tree (`benchmarks/agentic/fixtures/`).

**What SkillProof takes from it:** the losing-run ledger as a hard norm (commit
the run where your tool lost, with root cause); per-task breakdowns instead of
averages that hide blowups ("worst day" reporting); fixtures committed so runs
are reproducible.

## 4. ui-skills — curated registry + SKILL.md as the unit

**What the source tree shows.** Seven design-engineering skills
(`baseline-ui`, `create-design-md`, `fixing-accessibility`, `fixing-metadata`,
`fixing-motion-performance`, `improve-ui`, `ui-skills-root`), each a directory
with a `SKILL.md`; an Astro site; a CLI (`npx ui-skills start|categories|list|get`);
and an MCP endpoint exposing `list_skills` / `get_skill`.

- The repo doubles as the canonical example of the **SKILL.md bundle format**:
  a skill = markdown instructions (+ optional assets) in a known directory
  layout, consumable by agents and registries alike.

**What SkillProof takes from it:** SKILL.md bundles are the corpus format to
evaluate; registries already expose programmatic access (MCP), so corpus
acquisition can be scripted rather than hand-copied.

## 5. anti-slop — vendored quality rules with provenance

**What the source tree shows.** An Oxlint plugin with **18 generic rules + 5
Effect-specific rules**, every rule paired with a RuleTester test file
(`src/rules/*.test.ts`), a vendored copy of ESLint Stylistic with an `UPSTREAM.md`
provenance note, and an install path that is itself a skill
(`skills/install-anti-slop/SKILL.md`) doing three-way merges while preserving
local customizations and recording provenance for future updates.

- Distribution philosophy: **vendor, don't depend** — no npm package; `src/` is
  canonical and CI checks the skill's bundled copy stays identical
  (`sync:skill-assets` drift check).
- Rules are syntactic (ESTree + lexical scope), and the README documents exactly
  where enforcement is *intentionally local* rather than pretending whole-program
  analysis.

**What SkillProof takes from it:** provenance-preserving update mechanics for
anything copied into a corpus; paired rule/test symmetry as a quality bar;
documenting analysis boundaries instead of overselling reach.

---

## Cross-cutting observations

1. **SKILL.md won the format war, for now.** A scanner scans it (SkillSpector), a
   dev tool ships itself as one (Reticle), a registry distributes them (ui-skills),
   an installer is one (anti-slop), and a ruleset injector registers alongside
   them (Chisle). Any evaluation lab should treat the SKILL.md bundle as its
   primary corpus unit — with provenance (source repo + commit) recorded.
2. **Evidence culture is already a competitive feature.** Chisle commits its
   failures; Reticle publishes a limits table and a `unknown` verdict; anti-slop
   documents enforcement boundaries; SkillSpector documents fail-closed bounds.
   A 2026-era evaluation project that does not publish losses has no audience.
3. **Security is industrialized; effectiveness is not.** NVIDIA's pipeline has an
   "evaluate" stage but it is closed. Open tooling stops at "safe" (static),
   "cheap" (token rules), and "runs" (app verification). The effectiveness gap is
   real, open, and unowned.
4. **Every tool benchmarks itself, on its own fixtures.** There is no shared task
   suite, no shared result format, and no longitudinal re-running. Self-benchmarks
   are a start; they are not comparable across tools or over time.
5. **Model dependence is the elephant.** Skill effects depend on the driving model
   and agent harness, which change monthly. Any result format that does not pin
   model/agent/version is dead on arrival — and most published numbers today do
   not.
