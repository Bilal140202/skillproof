"""Hashing, run ids, host facts. Rule 5: provenance on every record."""

from __future__ import annotations

import datetime
import hashlib
import json
import platform
from pathlib import Path
from typing import Dict, Union


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Union[str, Path]) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_tree(root: Union[str, Path], excludes=()) -> Dict[str, object]:
    """Content hash over every file under ``root`` (sorted relpaths).

    ``excludes`` are relpath prefixes (a directory name excludes that dir).
    Returns {"sha256", "files", "bytes"} — stable across machines.
    """
    root = Path(root)
    h = hashlib.sha256()
    count = 0
    total = 0
    files = sorted(p for p in root.rglob("*") if p.is_file())
    for p in files:
        rel = p.relative_to(root).as_posix()
        if any(rel == e or rel.startswith(e.rstrip("/") + "/") for e in excludes):
            continue
        size = p.stat().st_size
        h.update(("%s\0%d\0%s\n" % (rel, size, sha256_file(p))).encode("utf-8"))
        count += 1
        total += size
    return {"sha256": h.hexdigest(), "files": count, "bytes": total}


def sha256_json(obj) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def make_run_id(parts: dict) -> str:
    """UTC timestamp + short hash of the measured inputs. Collisions are
    rejected by the runner (never overwrite evidence)."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return "%s-%s" % (stamp, sha256_json(parts)[:8])


def host_info() -> Dict[str, str]:
    return {"python": platform.python_version(), "os": platform.platform()}
