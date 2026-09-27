#!/usr/bin/env python3
"""Scripted demo agent — deterministic, no LLM, driven by the shell adapter.

Behavior matrix (by construction, to exercise every report shape):

  task   baseline            treatment                       report shape
  -----  ------------------  ------------------------------  ----------------
  t001   writes core, no     core + skill footer             fail -> pass
         footer                                              (improvement)
  t002   writes required     same                            pass -> pass
         sections                                            (neutral)
  t003   writes valid JSON   same                            pass -> pass
                                                              (neutral, outside
                                                              the skill's zone)
  t004   "Total: 42 items"   skill rule 4 -> "forty-two"     pass -> fail
                                                              (regression)
  t005   writes summary      writes summary, reports a       pass -> unknown
                              token total above the budget    (token_budget_
                                                              exceeded)

Token accounting: the treatment arm pays the skill instructions on every
session (EVALUATION.md §1) — +2500 tokens_in — plus task-specific self-
reported usage via .skillproof/agent_meta.json.
"""

import argparse
import json
import pathlib
import sys

FOOTER = "---\n*Prepared by the release desk*\n"
SKILL_SESSION_TOKENS = 2500
TAGS = ("t001", "t002", "t003", "t004", "t005")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--skill-dir", required=True)
    ap.add_argument("--arm", required=True, choices=["baseline", "treatment"])
    a = ap.parse_args()

    ws = pathlib.Path(a.workspace)
    (ws / ".skillproof").mkdir(parents=True, exist_ok=True)
    prompt = pathlib.Path(a.prompt_file).read_text(encoding="utf-8")
    tag = next((t for t in TAGS if ("[task:%s]" % t) in prompt), None)

    tokens_in = len(prompt.split()) * 3
    tokens_out = 40
    if a.arm == "treatment":
        tokens_in += SKILL_SESSION_TOKENS

    if tag == "t001":
        body = "# Release notes\n\n## Highlights\n\n- initial public release\n"
        if a.arm == "treatment":
            body += "\n" + FOOTER
        (ws / "RELEASE_NOTES.md").write_text(body, encoding="utf-8")
    elif tag == "t002":
        (ws / "RELEASE_NOTES.md").write_text(
            "# Release notes\n\n## Fixes\n\n- nothing yet\n\n"
            "## Known issues\n\n- TBD\n", encoding="utf-8")
    elif tag == "t003":
        data = ws / "data"
        data.mkdir(parents=True, exist_ok=True)
        (data / "stats.json").write_text('{"mean": 3.5}\n', encoding="utf-8")
    elif tag == "t004":
        line = "Total: forty-two items\n" if a.arm == "treatment" \
            else "Total: 42 items\n"
        (ws / "counts.txt").write_text(line, encoding="utf-8")
    elif tag == "t005":
        (ws / "SUMMARY.md").write_text("Scope: demo task five\n", encoding="utf-8")
        if a.arm == "treatment":
            tokens_in += 24000
            tokens_out += 1200
    else:
        # Unknown task: write nothing -> checks decide (an honest fail).
        pass

    meta = {"tokens_in": tokens_in, "tokens_out": tokens_out,
            "model": "scripted-demo-v0"}
    (ws / ".skillproof" / "agent_meta.json").write_text(
        json.dumps(meta), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
