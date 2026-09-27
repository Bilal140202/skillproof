"""Deterministic post-task checks. Three-valued: pass / fail / error.

``error`` is reserved for harness-side problems (missing binary, timeout,
ceiling exceeded, malformed check spec) and forces the task outcome to
``unknown`` — never a quiet pass, never a misleading fail (rule 3, rule 6).
A file the agent failed to produce is a *fail*: the evidence decided, and it
decided against. Everything here is deterministic code (rule 4).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Dict, Optional, Tuple

from .errors import SPError
from .provenance import sha256_bytes

PASS = "pass"
FAIL = "fail"
ERROR = "error"


@dataclass
class CheckResult:
    id: str
    type: str
    outcome: str
    detail: str
    duration_ms: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "type": self.type,
            "outcome": self.outcome,
            "detail": self.detail,
            "duration_ms": self.duration_ms,
        }


def safe_relpath(rel: str) -> Tuple[str, ...]:
    """Validate a task-side relative path (suite setup and check targets).

    Rejects absolute paths, traversal, empty parts, backslashes, and the
    reserved ``.skillproof/`` prefix (agent self-report directory).
    """
    if not isinstance(rel, str) or not rel or "\\" in rel:
        raise SPError("bad_path", "path must be a non-empty relative POSIX path")
    p = PurePosixPath(rel)
    if p.is_absolute() or not p.parts or ".." in p.parts:
        raise SPError("bad_path", "path must be relative and must not traverse up")
    if p.parts[0] == ".skillproof":
        raise SPError("bad_path", ".skillproof/ is reserved for agent self-reports")
    return p.parts


def _tail_text(blob: bytes, limit: int = 200) -> str:
    text = blob.decode("utf-8", errors="replace")
    if len(text) <= limit:
        return text
    return "…" + text[-limit:]


# --- individual checks: (spec, workspace, caps) -> (outcome, detail) ---------

def _file_exists(spec, workspace, caps):
    p = workspace.joinpath(*safe_relpath(spec["path"]))
    if p.exists():
        return PASS, "exists: %s" % spec["path"]
    return FAIL, "missing: %s" % spec["path"]


def _file_absent(spec, workspace, caps):
    p = workspace.joinpath(*safe_relpath(spec["path"]))
    if not p.exists():
        return PASS, "absent: %s" % spec["path"]
    return FAIL, "unexpectedly present: %s" % spec["path"]


def _read_capped(workspace, rel, caps):
    p = workspace.joinpath(*safe_relpath(rel))
    if not p.is_file():
        return None, None
    size = p.stat().st_size
    if size > caps.max_file_bytes:
        raise SPError("ceiling_file_too_big",
                      "%s is %d bytes (max_file_bytes=%d)" % (rel, size, caps.max_file_bytes))
    with open(p, "rb") as f:
        return f.read(), p


def _file_contains(spec, workspace, caps):
    blob, _ = _read_capped(workspace, spec["path"], caps)
    if blob is None:
        return FAIL, "file missing: %s" % spec["path"]
    text = blob.decode("utf-8", errors="replace")
    flags = re.IGNORECASE if spec.get("ignorecase") else 0
    if "text" in spec:
        if spec["text"] in text:
            return PASS, "substring found"
        return FAIL, "substring not found: %r" % spec["text"][:120]
    if re.search(spec["regex"], text, flags):
        return PASS, "regex matched"
    return FAIL, "regex not matched: %r" % spec["regex"][:120]


def _json_type_eq(a, b):
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


def _json_equals(spec, workspace, caps):
    blob, _ = _read_capped(workspace, spec["path"], caps)
    if blob is None:
        return FAIL, "file missing: %s" % spec["path"]
    try:
        doc = json.loads(blob.decode("utf-8"))
    except Exception as e:
        return FAIL, "invalid JSON: %s" % e
    node = doc
    for part in str(spec["key"]).split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.lstrip("-").isdigit():
            idx = int(part)
            if -len(node) <= idx < len(node):
                node = node[idx]
            else:
                return FAIL, "index out of range at %r" % part
        else:
            return FAIL, "key %r not found" % part
    if _json_type_eq(node, spec["expected"]):
        return PASS, "value equals expected"
    return FAIL, "got %r, expected %r" % (node, spec["expected"])[:200]


def _run_command(spec, workspace, caps, env_extra):
    command = spec["command"]
    argv = shlex.split(command) if isinstance(command, str) else list(command)
    if not argv:
        raise SPError("bad_check", "command expands to an empty argv")
    timeout = min(int(spec.get("timeout_s", 60)), caps.task_timeout_s)
    env = dict(os.environ)
    env.update(env_extra)
    try:
        proc = subprocess.run(
            argv, cwd=str(workspace), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, "check timeout after %ds" % timeout
    except OSError as e:
        return None, "failed to start: %s" % e
    return proc, None


def _command_ok(spec, workspace, caps):
    proc, err = _run_command(spec, workspace, caps, {"SKILLPROOF_CHECK": "1"})
    if err:
        return ERROR, err
    if proc.returncode == 0:
        return PASS, "exit 0"
    return FAIL, "exit %d: %s" % (proc.returncode, _tail_text(proc.stderr))


def _command_stdout(spec, workspace, caps):
    proc, err = _run_command(spec, workspace, caps, {"SKILLPROOF_CHECK": "1"})
    if err:
        return ERROR, err
    if proc.returncode != 0:
        return FAIL, "exit %d: %s" % (proc.returncode, _tail_text(proc.stderr))
    text = proc.stdout.decode("utf-8", errors="replace")
    flags = re.IGNORECASE if spec.get("ignorecase") else 0
    if "contains" in spec:
        if spec["contains"] in text:
            return PASS, "stdout contains expected text"
        return FAIL, "stdout missing %r" % spec["contains"][:120]
    if re.search(spec["regex"], text, flags):
        return PASS, "stdout matched regex"
    return FAIL, "stdout did not match %r" % spec["regex"][:120]


REGISTRY = {
    "file_exists": _file_exists,
    "file_absent": _file_absent,
    "file_contains": _file_contains,
    "json_equals": _json_equals,
    "command_ok": _command_ok,
    "command_stdout": _command_stdout,
}

# required and optional spec fields per check type (spec errors -> error outcome)
_SPEC_FIELDS = {
    "file_exists": ({"path"}, set()),
    "file_absent": ({"path"}, set()),
    "file_contains": ({"path"}, {"text", "regex", "ignorecase"}),
    "json_equals": ({"path", "key", "expected"}, set()),
    "command_ok": ({"command"}, {"timeout_s"}),
    "command_stdout": ({"command"}, {"contains", "regex", "ignorecase", "timeout_s"}),
}


def _spec_issues(ctype: str, spec: dict) -> Optional[str]:
    required, optional = _SPEC_FIELDS[ctype]
    unknown = set(spec) - {"type"} - required - optional
    if unknown:
        return "unknown field(s): %s" % ", ".join(sorted(unknown))
    missing = required - set(spec)
    if missing:
        return "missing field(s): %s" % ", ".join(sorted(missing))
    if ctype == "file_contains" and ("text" in spec) == ("regex" in spec):
        return "exactly one of 'text' or 'regex' is required"
    if ctype == "command_stdout" and ("contains" in spec) == ("regex" in spec):
        return "exactly one of 'contains' or 'regex' is required"
    if ctype in ("file_contains", "file_absent", "file_exists", "json_equals"):
        try:
            safe_relpath(spec["path"])
        except SPError as e:
            return str(e)
    return None


def apply_check(spec, index: int, workspace, caps) -> CheckResult:
    """Apply one check deterministically. Never raises: any failure inside a
    check becomes an ``error`` outcome, which the runner maps to ``unknown``."""
    cid = "checks[%d]" % index
    ctype = spec.get("type", "?") if isinstance(spec, dict) else "?"
    start = time.monotonic()
    try:
        if not isinstance(spec, dict) or "type" not in spec:
            outcome, detail = ERROR, "malformed check: not an object with a 'type' field"
        elif ctype not in REGISTRY:
            outcome, detail = ERROR, "unknown check type: %r" % (ctype,)
        else:
            issues = _spec_issues(ctype, spec)
            if issues:
                outcome, detail = ERROR, "malformed %s check: %s" % (ctype, issues)
            else:
                outcome, detail = REGISTRY[ctype](spec, workspace, caps)
    except SPError as e:
        outcome, detail = ERROR, "harness ceiling: %s" % e
    except Exception as e:  # noqa: BLE001 — a crashing check must not crash the run
        outcome, detail = ERROR, "check crashed: %s: %s" % (type(e).__name__, e)
    ms = int((time.monotonic() - start) * 1000)
    return CheckResult(cid, ctype, outcome, str(detail), ms)
