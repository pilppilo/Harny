"""Secure loading and rendering of local ``SKILL.md`` instructions."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


MAX_SKILL_BYTES = 64 * 1024


class SkillError(ValueError):
    """Raised when a skill directory is invalid or unsafe."""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    instructions: str
    path: str
    digest: str

    def metadata(self) -> dict[str, str]:
        return {"name": self.name, "description": self.description,
                "path": self.path, "sha256": self.digest}


def _frontmatter(text: str, path: Path) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise SkillError(f"{path}: SKILL.md must start with YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise SkillError(f"{path}: unterminated YAML frontmatter")
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise SkillError(f"{path}: malformed frontmatter line")
        if key.strip() not in {"name", "description"}:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    for key in ("name", "description"):
        if not values.get(key):
            raise SkillError(f"{path}: frontmatter requires {key}")
    return values, text[end + len("\n---\n"):].lstrip()


def load_skill(root: str | os.PathLike[str]) -> Skill:
    """Load one skill from a directory containing ``SKILL.md``.

    The file must be regular, non-symlinked, and remain beneath the supplied
    directory after resolution. No other skill files are read or executed.
    """
    supplied = Path(root).expanduser()
    if supplied.name == "SKILL.md" and supplied.is_file():
        supplied = supplied.parent
    base = supplied.resolve(strict=True)
    if not base.is_dir():
        raise SkillError(f"skill root is not a directory: {root}")
    skill_path = base / "SKILL.md"
    if skill_path.is_symlink() or not skill_path.is_file():
        raise SkillError(f"missing regular SKILL.md in {base}")
    resolved = skill_path.resolve(strict=True)
    if resolved.parent != base:
        raise SkillError(f"SKILL.md escapes skill root: {skill_path}")
    size = skill_path.stat().st_size
    if size > MAX_SKILL_BYTES:
        raise SkillError(f"{skill_path}: exceeds {MAX_SKILL_BYTES} byte limit")
    raw = skill_path.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    meta, body = _frontmatter(text, skill_path)
    return Skill(meta["name"], meta["description"], body,
                 str(skill_path), hashlib.sha256(raw).hexdigest())


def render_skill_instructions(skills: list[Skill] | tuple[Skill, ...]) -> str:
    if not skills:
        return ""
    blocks = ["\n\n# Local skills\n",
              "The following trusted local skill instructions apply to this request:\n"]
    for skill in skills:
        blocks.append(f"\n## {skill.name}\n{skill.description}\n\n{skill.instructions}\n")
    return "".join(blocks).rstrip()


def load_skills(paths: list[str] | tuple[str, ...] | None) -> list[Skill]:
    return [load_skill(path) for path in (paths or [])]
