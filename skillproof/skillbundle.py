"""Skill bundle loader: a directory containing SKILL.md (the format the whole
ecosystem already distributes, per LANDSCAPE.md). Tree-hashed (rule 5)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from .errors import SPError
from .provenance import sha256_file, sha256_tree

MAX_SKILL_FILES = 200
MAX_SKILL_BYTES = 5_000_000
MAX_SKILL_MD_BYTES = 200_000


@dataclass
class SkillBundle:
    name: str
    description: str
    path: Path
    sha256: str
    file_count: int
    frontmatter: Dict[str, str]


def _frontmatter(text: str) -> Dict[str, str]:
    """Flat ``key: value`` YAML frontmatter — deliberately minimal. A skill
    whose frontmatter does not parse still loads (name falls back to the
    directory name); the harness measures behavior, not metadata."""
    fm: Dict[str, str] = {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return fm
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line and len(fm) < 32:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and val:
                fm[key] = val[:300]
    return fm


def load_skill(path) -> SkillBundle:
    path = Path(path)
    if not path.is_dir():
        raise SPError("missing_input", "skill not found (must be a directory): %s" % path)
    md = path / "SKILL.md"
    if not md.is_file():
        raise SPError("bad_skill", "skill directory must contain SKILL.md: %s" % path)
    md_size = md.stat().st_size
    if md_size == 0:
        raise SPError("bad_skill", "SKILL.md is empty")
    if md_size > MAX_SKILL_MD_BYTES:
        raise SPError("ceiling_skill_md", "SKILL.md is %d bytes (ceiling %d)"
                      % (md_size, MAX_SKILL_MD_BYTES))
    files = sorted(p for p in path.rglob("*") if p.is_file())
    if len(files) > MAX_SKILL_FILES:
        raise SPError("ceiling_skill_files",
                      "skill has %d files (ceiling %d)" % (len(files), MAX_SKILL_FILES))
    total = sum(p.stat().st_size for p in files)
    if total > MAX_SKILL_BYTES:
        raise SPError("ceiling_skill_bytes",
                      "skill is %d bytes (ceiling %d)" % (total, MAX_SKILL_BYTES))
    fm = _frontmatter(md.read_text(encoding="utf-8", errors="replace"))
    tree = sha256_tree(path)
    return SkillBundle(
        name=fm.get("name") or path.name,
        description=fm.get("description", ""),
        path=path,
        sha256=tree["sha256"],
        file_count=tree["files"],
        frontmatter=fm,
    )
