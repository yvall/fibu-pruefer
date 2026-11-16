from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SkillManifest:
    skill_id: str
    name: str = ""
    description: str = ""
    kind: str = "code"
    runs_after: list[str] = field(default_factory=list)
    severity_default: str = "fehler"
    inputs: list[str] = field(default_factory=list)
    check_path: Path = field(default_factory=Path)
    braucht_llm: bool = False


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    parsed = yaml.safe_load(text[3:end])
    return parsed if isinstance(parsed, dict) else {}


def load_manifests(skills_dir: Path) -> list[SkillManifest]:
    """Lädt alle SKILL.md-Dateien aus skills_dir und gibt sortierte Manifeste zurück."""
    manifests: list[SkillManifest] = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skill_id = skill_md.parent.name
        try:
            fm = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError) as exc:
            warnings.warn(f"Skill {skill_id}: SKILL.md nicht lesbar – {exc}", RuntimeWarning, stacklevel=2)
            fm = {}
        manifests.append(
            SkillManifest(
                skill_id=skill_id,
                name=str(fm.get("name") or skill_id),
                description=str(fm.get("description") or ""),
                kind=str(fm.get("kind") or "code"),
                runs_after=[str(x) for x in (fm.get("runs_after") or [])],
                severity_default=str(fm.get("severity_default") or "fehler"),
                inputs=[str(x) for x in (fm.get("inputs") or [])],
                check_path=skill_md.parent / "check.py",
                braucht_llm=bool(fm.get("llm")),
            )
        )
    return manifests
