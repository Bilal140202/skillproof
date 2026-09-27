"""Harness config loader. Strict schema, declared ceilings (rule 6).

Config schema ``skillproof.config/0.1`` — see docs/FORMATS.md.
"""

from __future__ import annotations

import json
import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .errors import SPError

SCHEMA = "skillproof.config/0.1"
_TOP_KEYS = {"schema", "adapter", "model", "caps", "notes"}
_TEMPLATE_FIELDS = {"workspace", "prompt_file", "skill_dir", "arm", "run_dir", "suite_dir"}
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class Caps:
    task_timeout_s: int
    run_timeout_s: int
    max_output_bytes: int
    token_budget: Optional[int]
    max_workspace_files: int
    max_file_bytes: int


@dataclass
class Config:
    adapter_type: str
    command_template: str
    env: Dict[str, str]
    model: Optional[dict]
    notes: Optional[str]
    caps: Caps
    sha256: str
    path: Path


def _reject(msg: str):
    raise SPError("bad_config", msg)


def _caps(raw: dict) -> Caps:
    if not isinstance(raw, dict):
        _reject("caps must be an object")
    allowed = {"task_timeout_s", "run_timeout_s", "max_output_bytes",
               "token_budget", "max_workspace_files", "max_file_bytes"}
    unknown = set(raw) - allowed
    if unknown:
        _reject("unknown caps field(s): %s" % ", ".join(sorted(unknown)))

    def _int(key, default, lo, hi):
        v = raw.get(key, default)
        if not isinstance(v, int) or isinstance(v, bool) or not (lo <= v <= hi):
            _reject("caps.%s must be an int in %d..%d" % (key, lo, hi))
        return v

    token_budget = raw.get("token_budget")
    if token_budget is not None and \
            (not isinstance(token_budget, int) or isinstance(token_budget, bool)
             or token_budget < 100):
        _reject("caps.token_budget must be an int >= 100 (self-reported tokens)")
    return Caps(
        task_timeout_s=_int("task_timeout_s", 120, 1, 3600),
        run_timeout_s=_int("run_timeout_s", 1800, 1, 86400),
        max_output_bytes=_int("max_output_bytes", 65_536, 1024, 10_485_760),
        token_budget=token_budget,
        max_workspace_files=_int("max_workspace_files", 2000, 1, 100_000),
        max_file_bytes=_int("max_file_bytes", 1_000_000, 1024, 100_000_000),
    )


def load_config(path) -> Config:
    path = Path(path)
    if not path.is_file():
        raise SPError("missing_input", "config not found: %s" % path)
    raw = path.read_bytes()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except Exception as e:
        _reject("config is not valid JSON: %s" % e)
    if not isinstance(doc, dict):
        _reject("config must be a JSON object")
    unknown = set(doc) - _TOP_KEYS
    if unknown:
        _reject("unknown config field(s): %s" % ", ".join(sorted(unknown)))
    if doc.get("schema") != SCHEMA:
        _reject("config schema must be %r (got %r)" % (SCHEMA, doc.get("schema")))

    adapter = doc.get("adapter")
    if not isinstance(adapter, dict):
        _reject("config 'adapter' must be an object")
    if set(adapter) - {"type", "command_template", "env"}:
        _reject("adapter allows only fields: type, command_template, env")
    if adapter.get("type") != "shell":
        _reject("adapter.type must be 'shell' (harness v0 drives local CLI agents; "
                "API adapters are future work)")
    template = adapter.get("command_template")
    if not isinstance(template, str) or not template.strip():
        _reject("adapter.command_template must be a non-empty string")
    fields = {fname for _, fname, _, _ in string.Formatter().parse(template) if fname}
    if not {"workspace", "prompt_file"} <= fields:
        _reject("command_template must reference at least {workspace} and {prompt_file}")
    if not fields <= _TEMPLATE_FIELDS:
        _reject("command_template uses unknown placeholder(s): %s (allowed: %s)"
                % (", ".join(sorted(fields - _TEMPLATE_FIELDS)),
                   ", ".join(sorted(_TEMPLATE_FIELDS))))
    env_raw = adapter.get("env", {})
    if not isinstance(env_raw, dict) or len(env_raw) > 32:
        _reject("adapter.env must be an object with at most 32 entries")
    for k, v in env_raw.items():
        if not isinstance(k, str) or not _ENV_KEY_RE.match(k):
            _reject("adapter.env key %r is not a valid environment variable name" % (k,))
        if not isinstance(v, str) or len(v) > 4096:
            _reject("adapter.env value for %r must be a string of at most 4096 chars" % (k,))

    model = doc.get("model")
    if model is not None:
        if not isinstance(model, dict) or not isinstance(model.get("name"), str) \
                or not model.get("name"):
            _reject("config 'model' (when present) must be an object with a non-empty 'name'")
        if "pinned" in model and not isinstance(model["pinned"], bool):
            _reject("config 'model.pinned' must be a boolean")
    notes = doc.get("notes")
    if notes is not None and not isinstance(notes, str):
        _reject("config 'notes' must be a string")

    from .provenance import sha256_bytes
    return Config(
        adapter_type="shell",
        command_template=template,
        env=dict(env_raw),
        model=model,
        notes=notes,
        caps=_caps(doc.get("caps", {})),
        sha256=sha256_bytes(raw),
        path=path,
    )
