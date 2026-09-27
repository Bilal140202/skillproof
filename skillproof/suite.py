"""Task suite loader. Strict schema: unknown fields are rejected (fail-closed).

Suite schema ``skillproof.suite/0.1`` — see docs/FORMATS.md.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import checks
from .errors import SPError

SCHEMA = "skillproof.suite/0.1"
MAX_TASKS = 500
MAX_SETUP_BYTES = 1_000_000
MAX_PROMPT_CHARS = 20_000

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_TASK_KEYS = {"id", "prompt", "checks", "setup", "timeout_s", "tags", "notes"}
_TOP_KEYS = {"schema", "name", "description", "tasks"}


@dataclass
class Task:
    id: str
    prompt: str
    checks: List[dict]
    setup: List[Tuple[str, bytes]]
    timeout_s: Optional[int]
    tags: List[str]
    notes: Optional[str]


@dataclass
class Suite:
    name: str
    description: str
    tasks: List[Task]
    sha256: str
    path: Path


def _reject(msg: str):
    raise SPError("bad_suite", msg)


def _parse_setup(raw: dict, where: str) -> List[Tuple[str, bytes]]:
    setup: List[Tuple[str, bytes]] = []
    total = 0
    for rel, val in raw.items():
        try:
            checks.safe_relpath(rel)
        except SPError as e:
            _reject("%s: setup path %r: %s" % (where, rel, e))
        if isinstance(val, str):
            blob = val.encode("utf-8")
        elif isinstance(val, dict) and set(val) <= {"content", "encoding"} \
                and isinstance(val.get("content"), str) \
                and val.get("encoding", "utf8") in ("utf8", "base64"):
            if val.get("encoding", "utf8") == "base64":
                try:
                    blob = base64.b64decode(val["content"], validate=True)
                except Exception as e:
                    _reject("%s: setup %r: bad base64: %s" % (where, rel, e))
            else:
                blob = val["content"].encode("utf-8")
        else:
            _reject("%s: setup %r must be a string or {content, encoding}" % (where, rel))
        total += len(blob)
        if total > MAX_SETUP_BYTES:
            _reject("%s: total setup bytes exceed %d" % (where, MAX_SETUP_BYTES))
        setup.append((rel, blob))
    return setup


def load_suite(path) -> Suite:
    path = Path(path)
    if not path.is_file():
        raise SPError("missing_input", "suite not found: %s" % path)
    raw = path.read_bytes()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except Exception as e:
        _reject("suite is not valid JSON: %s" % e)
    if not isinstance(doc, dict):
        _reject("suite must be a JSON object")
    unknown = set(doc) - _TOP_KEYS
    if unknown:
        _reject("unknown suite field(s): %s" % ", ".join(sorted(unknown)))
    if doc.get("schema") != SCHEMA:
        _reject("suite schema must be %r (got %r)" % (SCHEMA, doc.get("schema")))
    name = doc.get("name")
    if not isinstance(name, str) or not (1 <= len(name) <= 80):
        _reject("suite 'name' must be a string of 1..80 chars")
    description = doc.get("description", "")
    if not isinstance(description, str):
        _reject("suite 'description' must be a string")
    tasks_raw = doc.get("tasks")
    if not isinstance(tasks_raw, list) or not (1 <= len(tasks_raw) <= MAX_TASKS):
        _reject("suite 'tasks' must be a list of 1..%d tasks" % MAX_TASKS)

    tasks: List[Task] = []
    seen = set()
    for i, t in enumerate(tasks_raw):
        where = "tasks[%d]" % i
        if not isinstance(t, dict):
            _reject("%s: task must be an object" % where)
        unknown = set(t) - _TASK_KEYS
        if unknown:
            _reject("%s: unknown task field(s): %s" % (where, ", ".join(sorted(unknown))))
        tid = t.get("id")
        if not isinstance(tid, str) or not _ID_RE.match(tid):
            _reject("%s: 'id' must match %s (got %r)" % (where, _ID_RE.pattern, tid))
        if tid in seen:
            _reject("%s: duplicate task id %r" % (where, tid))
        seen.add(tid)
        prompt = t.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            _reject("%s: 'prompt' must be a non-empty string" % where)
        if len(prompt) > MAX_PROMPT_CHARS:
            _reject("%s: 'prompt' exceeds %d chars" % (where, MAX_PROMPT_CHARS))
        checks_raw = t.get("checks")
        if not isinstance(checks_raw, list) or not (1 <= len(checks_raw) <= 20):
            _reject("%s: 'checks' must be a list of 1..20 checks" % where)
        for j, c in enumerate(checks_raw):
            if not isinstance(c, dict) or "type" not in c:
                _reject("%s: checks[%d] must be an object with a 'type' field" % (where, j))
            if c["type"] not in checks.REGISTRY:
                _reject("%s: checks[%d] unknown check type %r"
                        % (where, j, c.get("type")))
        timeout_s = t.get("timeout_s")
        if timeout_s is not None and \
                (not isinstance(timeout_s, int) or isinstance(timeout_s, bool)
                 or not (1 <= timeout_s <= 3600)):
            _reject("%s: 'timeout_s' must be an int in 1..3600" % where)
        tags = t.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(x, str) for x in tags):
            _reject("%s: 'tags' must be a list of strings" % where)
        notes = t.get("notes")
        if notes is not None and not isinstance(notes, str):
            _reject("%s: 'notes' must be a string" % where)
        tasks.append(Task(
            id=tid,
            prompt=prompt,
            checks=checks_raw,
            setup=_parse_setup(t.get("setup") or {}, where),
            timeout_s=timeout_s,
            tags=tags,
            notes=notes,
        ))

    from .provenance import sha256_bytes
    return Suite(name=name, description=description, tasks=tasks,
                 sha256=sha256_bytes(raw), path=path)
