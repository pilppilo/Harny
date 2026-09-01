from pathlib import Path

import pytest

from vharness.skills import MAX_SKILL_BYTES, SkillError, load_skill, load_skills, render_skill_instructions


def write_skill(root: Path, body: str = "Do the safe thing.\n", *, ending: str = "\n") -> Path:
    root.mkdir()
    path = root / "SKILL.md"
    path.write_text(f"---{ending}name: example{ending}description: Example skill{ending}author: test{ending}---{ending}{body}", encoding="utf-8", newline="")
    return path


def test_load_and_render_skill(tmp_path):
    path = write_skill(tmp_path / "example")
    skill = load_skill(path.parent)
    assert skill.name == "example"
    assert skill.description == "Example skill"
    assert "Do the safe thing." in render_skill_instructions([skill])
    assert len(skill.digest) == 64


def test_crlf_and_unknown_frontmatter_are_supported(tmp_path):
    skill = load_skill(write_skill(tmp_path / "example", ending="\r\n").parent)
    assert skill.name == "example"


@pytest.mark.parametrize("content", ["name: missing delimiters\n", "---\nname: x\n---\n"])
def test_invalid_frontmatter_rejected(tmp_path, content):
    root = tmp_path / "bad"
    root.mkdir()
    (root / "SKILL.md").write_text(content, encoding="utf-8")
    with pytest.raises(SkillError):
        load_skill(root)


def test_oversized_skill_rejected(tmp_path):
    path = write_skill(tmp_path / "large", "x" * MAX_SKILL_BYTES)
    with pytest.raises(SkillError, match="byte limit"):
        load_skill(path.parent)


def test_symlink_skill_rejected(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("---\nname: x\ndescription: y\n---\n", encoding="utf-8")
    root = tmp_path / "linked"
    root.mkdir()
    (root / "SKILL.md").symlink_to(outside)
    with pytest.raises(SkillError):
        load_skill(root)


def test_load_skills_empty_and_multiple(tmp_path):
    a = write_skill(tmp_path / "a")
    b = write_skill(tmp_path / "b")
    assert load_skills(None) == []
    assert [s.name for s in load_skills([str(a.parent), str(b.parent)])] == ["example", "example"]
