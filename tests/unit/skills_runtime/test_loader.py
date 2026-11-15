from pathlib import Path

import pytest

from fibu.skills_runtime.loader import SkillManifest, _parse_frontmatter, load_manifests


SKILL_MD_FULL = """\
---
name: bwa-rechenwege
description: Prüft BWA-Arithmetik
kind: code
runs_after: []
severity_default: fehler
inputs:
  - auswertung
---
# BWA-Rechenwege
Prüft, ob alle BWA-Summenzeilen stimmen.
"""

SKILL_MD_WITH_DEPS = """\
---
name: klaerungsliste
kind: code
runs_after:
  - vormonat-fortschreibung
  - belege-abgleich
inputs:
  - auswertung
  - belege
  - klaerung
---
"""

SKILL_MD_NO_FRONTMATTER = "# Kein Frontmatter\nIrgendein Text."


def test_parse_frontmatter_full():
    fm = _parse_frontmatter(SKILL_MD_FULL)
    assert fm["name"] == "bwa-rechenwege"
    assert fm["kind"] == "code"
    assert fm["inputs"] == ["auswertung"]
    assert fm["runs_after"] == []


def test_parse_frontmatter_with_deps():
    fm = _parse_frontmatter(SKILL_MD_WITH_DEPS)
    assert fm["runs_after"] == ["vormonat-fortschreibung", "belege-abgleich"]
    assert "klaerung" in fm["inputs"]


def test_parse_frontmatter_no_frontmatter():
    fm = _parse_frontmatter(SKILL_MD_NO_FRONTMATTER)
    assert fm == {}


def test_load_manifests_single_skill(tmp_path: Path) -> None:
    skill_dir = tmp_path / "bwa-rechenwege"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(SKILL_MD_FULL)
    (skill_dir / "check.py").write_text("")

    manifests = load_manifests(tmp_path)
    assert len(manifests) == 1
    m = manifests[0]
    assert m.skill_id == "bwa-rechenwege"
    assert m.name == "bwa-rechenwege"
    assert m.kind == "code"
    assert m.runs_after == []
    assert m.inputs == ["auswertung"]
    assert m.check_path == skill_dir / "check.py"


def test_load_manifests_sorted_alphabetically(tmp_path: Path) -> None:
    for name in ("zzz-skill", "aaa-skill", "mmm-skill"):
        d = tmp_path / name
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
    manifests = load_manifests(tmp_path)
    ids = [m.skill_id for m in manifests]
    assert ids == sorted(ids)


def test_load_manifests_with_deps(tmp_path: Path) -> None:
    skill_dir = tmp_path / "klaerungsliste"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(SKILL_MD_WITH_DEPS)
    manifests = load_manifests(tmp_path)
    m = manifests[0]
    assert "vormonat-fortschreibung" in m.runs_after
    assert "belege-abgleich" in m.runs_after


def test_load_manifests_empty_dir(tmp_path: Path) -> None:
    assert load_manifests(tmp_path) == []


def test_load_manifests_missing_check_py(tmp_path: Path) -> None:
    skill_dir = tmp_path / "ohne-check"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: ohne-check\n---\n")
    manifests = load_manifests(tmp_path)
    # Manifest wird trotzdem geladen; check_path wird gesetzt aber existiert nicht
    assert len(manifests) == 1
    assert not manifests[0].check_path.exists()


def test_load_manifests_defaults_for_minimal_frontmatter(tmp_path: Path) -> None:
    skill_dir = tmp_path / "minimal"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\n---\n")
    manifests = load_manifests(tmp_path)
    m = manifests[0]
    assert m.skill_id == "minimal"
    assert m.name == "minimal"  # Fallback auf skill_id
    assert m.kind == "code"
    assert m.runs_after == []
    assert m.severity_default == "fehler"
