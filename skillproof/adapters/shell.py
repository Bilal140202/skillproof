"""Shell adapter — the only agent adapter in harness v0 (ADR-2).

It drives ANY local CLI agent through a command template (local-first, rule 8):
    <agent-cli> --workspace {workspace} --prompt-file {prompt_file} \
                --skill-dir {skill_dir} --arm {arm}
The prompt is byte-identical in both arms; only ``--skill-dir`` (and the
SKILLPROOF_ARM env var) differ. Token counts are *self-reported* by the agent
via ``<workspace>/.skillproof/agent_meta.json`` and are null when absent —
the harness never infers cost it cannot see.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from ..errors import SPError

META_DIR = ".skillproof"
META_FILE = "agent_meta.json"


@dataclass
class AgentRun:
    exit_code: Optional[int]
    timed_out: bool
    exec_error: Optional[str]
    duration_ms: int
    stdout_tail: str
    stderr_tail: str
    meta: Optional[Dict[str, object]]
    meta_note: Optional[str]


def _tail(blob: bytes, cap: int) -> str:
    if len(blob) <= cap:
        return blob.decode("utf-8", errors="replace")
    return "[truncated — showing last %d of %d bytes]\n%s" % (
        cap, len(blob), blob[-cap:].decode("utf-8", errors="replace"))


def _read_meta(workspace: Path):
    """Contract: agent MAY write {tokens_in:int, tokens_out:int, model:str} to
    ``<workspace>/.skillproof/agent_meta.json``. Anything malformed is ignored
    with a note — never trusted blindly, never crashy."""
    p = workspace / META_DIR / META_FILE
    if not p.is_file():
        return None, None
    try:
        doc = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        return None, "agent_meta.json is not valid JSON (ignored): %s" % e
    if not isinstance(doc, dict):
        return None, "agent_meta.json is not an object (ignored)"
    meta: Dict[str, object] = {"reported": True}
    notes = []
    for key in ("tokens_in", "tokens_out"):
        v = doc.get(key)
        if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
            meta[key] = v
        else:
            meta[key] = None
            notes.append("%s missing or not a non-negative int" % key)
    model = doc.get("model")
    if isinstance(model, str) and model and len(model) <= 200:
        meta["model"] = model
    else:
        meta["model"] = None
        notes.append("model missing or not a short string")
    return meta, ("; ".join(notes) if notes else None)


def run_agent(config, workspace: Path, prompt_text: str, prompt_file: Path,
              skill_dir: Path, arm: str, caps, run_dir: Path,
              suite_dir: Path, task_timeout_s: int) -> AgentRun:
    start = time.monotonic()
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt_text, encoding="utf-8")

    # Template values MUST be absolute: the agent subprocess runs with
    # cwd=workspace, so any relative path in the command line would silently
    # resolve elsewhere (found by the first dogfood run; see results/ ledger).
    filled = config.command_template.format(
        workspace=str(workspace.resolve()),
        prompt_file=str(prompt_file.resolve()),
        skill_dir=str(skill_dir.resolve()),
        arm=arm,
        run_dir=str(run_dir.resolve()),
        suite_dir=str(suite_dir.resolve()),
    )
    argv = shlex.split(filled)
    if not argv:
        raise SPError("bad_config", "command_template expands to an empty command")

    env = dict(os.environ)
    env.update(config.env)
    env["SKILLPROOF_ARM"] = arm
    env["SKILLPROOF_WORKSPACE"] = str(workspace.resolve())

    try:
        proc = subprocess.run(
            argv, cwd=str(workspace), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=task_timeout_s,
        )
        exit_code, timed_out, exec_error = proc.returncode, False, None
        out, err = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        exit_code, timed_out, exec_error = None, True, None
        out, err = e.stdout or b"", e.stderr or b""
    except OSError as e:
        exit_code, timed_out, exec_error = None, False, "failed to start: %s" % e
        out, err = b"", b""

    duration_ms = int((time.monotonic() - start) * 1000)
    stdout_tail = _tail(out, caps.max_output_bytes)
    stderr_tail = _tail(err, caps.max_output_bytes)
    log_path = prompt_file.parent / "agent.log"
    log_path.write_text(
        "--- command ---\n%s\n--- exit_code=%s timed_out=%s exec_error=%s ---\n"
        "--- stdout ---\n%s\n--- stderr ---\n%s\n"
        % (filled, exit_code, timed_out, exec_error, stdout_tail, stderr_tail),
        encoding="utf-8",
    )
    meta, meta_note = _read_meta(workspace)
    return AgentRun(exit_code, timed_out, exec_error, duration_ms,
                    stdout_tail, stderr_tail, meta, meta_note)
