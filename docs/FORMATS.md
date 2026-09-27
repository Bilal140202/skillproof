# Formats — v0.1 (DRAFT, finalized by issue #4)

All formats are JSON, UTF-8, strict: unknown fields are rejected at load
(fail-closed). Every schema carries a `schema` string; breaking changes bump
the minor version and old records keep validating against their pinned schema.
Status: **DRAFT** until issue #4 lands; the harness writes what it measures,
nothing more.

## 1. Task suite — `skillproof.suite/0.1`

```json
{
  "schema": "skillproof.suite/0.1",
  "name": "release-notes-basics",
  "description": "optional",
  "tasks": [
    {
      "id": "t001-summary-line",
      "prompt": "the exact prompt the agent receives (byte-identical in both arms)",
      "setup": {
        "input/draft.md": "seed file content",
        "bin/blob": {"content": "AAEC", "encoding": "base64"}
      },
      "checks": [
        {"type": "file_exists", "path": "RELEASE_NOTES.md"},
        {"type": "file_contains", "path": "RELEASE_NOTES.md", "text": "## Highlights"},
        {"type": "file_contains", "path": "out.txt", "regex": "^ok$", "ignorecase": true},
        {"type": "file_absent", "path": "scratch.tmp"},
        {"type": "json_equals", "path": "data/stats.json", "key": "mean", "expected": 3.5},
        {"type": "command_ok", "command": ["python3", "-c", "import json;json.load(open('data/stats.json'))"]},
        {"type": "command_stdout", "command": ["make", "test"], "contains": "passed", "timeout_s": 30}
      ],
      "timeout_s": 120,
      "tags": ["compliance"],
      "notes": "why this task exists"
    }
  ]
}
```

Constraints: 1..500 tasks; ids `^[a-z0-9][a-z0-9_.-]{0,63}$`, unique; 1..20
checks per task; setup paths are relative POSIX paths (no `..`, no absolute,
`.skillproof/` reserved); total setup <= 1,000,000 bytes; prompt <= 20,000
chars. Task tags like `[task:t001]` inside prompts are a demo-only convention
of the scripted agent, not part of the schema.

Check semantics — the three-valued contract:

| situation | outcome |
| --- | --- |
| evidence satisfies the spec | `pass` |
| evidence violates the spec (incl. file the agent should have produced) | `fail` |
| harness-side problem: spec malformed, binary missing, check timeout, file exceeds `max_file_bytes`, checker crash | `error` → task outcome `unknown` |

`error` is never allowed to masquerade as pass or fail (rule 3).

## 2. Harness config — `skillproof.config/0.1`

```json
{
  "schema": "skillproof.config/0.1",
  "adapter": {
    "type": "shell",
    "command_template": "your-agent-cli --workdir {workspace} --task-file {prompt_file} --skills {skill_dir} --arm {arm}",
    "env": {"MY_AGENT_QUIET": "1"}
  },
  "model": {"name": "vendor/model-id@revision", "pinned": true},
  "caps": {
    "task_timeout_s": 120,
    "run_timeout_s": 1800,
    "max_output_bytes": 65536,
    "token_budget": 20000,
    "max_workspace_files": 2000,
    "max_file_bytes": 1000000
  },
  "notes": "why this config exists"
}
```

`command_template` placeholders: `{workspace}` and `{prompt_file}` required;
`{skill_dir}`, `{arm}`, `{run_dir}`, `{suite_dir}` optional. Expansion is
argv-split (no shell features — no pipes, no globs; wrap complexity in your
own script). Environment given to the agent: os environ + `adapter.env` +
`SKILLPROOF_ARM=baseline|treatment` + `SKILLPROOF_WORKSPACE=<abs path>`.

Caps are ceilings, not suggestions (rule 6): a hit is *recorded*, never a
hang. `token_budget` compares the agent's self-reported total
(`tokens_in + tokens_out`) against the ceiling.

## 3. Skill bundle

A directory containing `SKILL.md` (the format the ecosystem already
distributes — LANDSCAPE.md). Optional flat `key: value` YAML frontmatter;
`name` falls back to the directory name when absent or unparseable. Ceilings:
200 files, 5 MB total, 200 KB for SKILL.md. The bundle is tree-hashed;
`inputs/skill/` stores a byte-identical copy in every run.

## 4. Delta report — `skillproof.delta-report/0.1`

One file per run: `results/<run_id>/run.json` (plus a rendered
`REPORT.md`). Structure:

```
schema, schema_status            -> "skillproof.delta-report/0.1", DRAFT note
run_id                           -> <UTC timestamp>-<8 hex of input hashes>
run_status                       -> "complete" | "aborted" (deadline hit)
collected_at                     -> ISO-8601 UTC
harness                          -> version, python, os
provenance
  suite                          -> path, name, sha256, task_count
  skill                          -> name, path, sha256, files (null if none)
  config                         -> path, sha256, adapter, model
  order                          -> pairing/order statement
  staleness                      -> collected_at, model_pinned, note   (G4)
arms_summary                     -> per arm: pass/fail/unknown counts,
                                    reported token sums, wall ms total
tasks[]
  task_id
  baseline / treatment            -> arm records (below)
  outcome_shift                   -> "<baseline>-><treatment>"
  checks_pass_delta               -> int | null
  tokens_delta                    -> int | null (null unless BOTH arms report)
  duration_delta_ms               -> int | null
  improvement / regression        -> fail->pass / pass->fail booleans
limits[]                         -> the limits table, same file as numbers (rule 7)
```

Arm record (written twice per task, also to
`raw/<task_id>/<arm>/meta.json`):

```
arm, outcome (pass|fail|unknown), reason_code
checks[]          -> id, type, outcome, detail, duration_ms
agent             -> exit_code, timed_out, exec_error, duration_ms,
                     log_file, log_sha256
metrics           -> tokens_in, tokens_out, model, reported
side_effects      -> files_added[], files_removed[], files_modified[],
                     agent_workspace_sha256 (pre-check tree, excl. .skillproof),
                     snapshot_truncated, files_after{path: sha}
caps              -> task_timeout_s, max_output_bytes, token_budget, flags[]
provenance        -> prompt_sha256, prompt_file, workspace,
                     post_check_workspace_sha256 (whole workspace tree),
                     skill_sha256 (treatment arm only)
```

### Unknown reason codes

| code | meaning |
| --- | --- |
| `agent_exec_error` | agent command could not start (missing binary etc.) |
| `agent_timeout` | agent exceeded the task wall-clock ceiling |
| `token_budget_exceeded` | self-reported tokens exceeded `caps.token_budget` |
| `check_error:checks[i]` | check i errored (malformed spec, missing binary, ceiling, crash) |
| `checks_failed` | informational: outcome `fail`, >=1 check failed |
| `run_deadline_exceeded` | run-level wall clock hit before this arm started |
| `harness_error` | unexpected harness exception while running this arm |

### Agent self-report contract

An agent MAY write `<workspace>/.skillproof/agent_meta.json`:

```json
{"tokens_in": 15234, "tokens_out": 812, "model": "vendor/model@rev"}
```

Types are validated; anything malformed is ignored and noted in
`caps.flags` (`agent_meta_note: ...`). Cost deltas are computed only when
BOTH arms report — the harness never invents a number it cannot see. The
`.skillproof/` directory is excluded from side-effect manifests.

## 5. Run directory layout

```
results/<run_id>/
  run.json                     # machine-readable record (validated before write)
  REPORT.md                    # human-readable rendering
  inputs/suite.json            # byte-identical copies
  inputs/config.json
  inputs/skill/...             # byte-identical skill copy
  raw/<task_id>/<arm>/prompt.txt
  raw/<task_id>/<arm>/agent.log
  raw/<task_id>/<arm>/agent_meta.json   # copy of the self-report, if any
  raw/<task_id>/<arm>/meta.json         # arm record (verify: == run.json entry)
  raw/<task_id>/<arm>/workspace/        # workspace snapshot
```

`skillproof verify --run <dir>` recomputes: inputs hashes, skill tree hash,
per-arm prompt hashes, workspace tree hashes, meta.json↔run.json equality.
Any drift fails with exit 1 — committed runs are tamper-evident.
