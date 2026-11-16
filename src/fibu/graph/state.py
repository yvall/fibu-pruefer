from __future__ import annotations

from typing import TypedDict

from fibu.contracts import Context
from fibu.skills_runtime import SkillResult


class _PruefStateBasis(TypedDict):
    """Pflichtfelder – müssen im Initialzustand gesetzt sein."""

    ordner: str
    skills_dir: str
    config: dict[str, object]


class PruefState(_PruefStateBasis, total=False):
    """Vollständiger Graph-State; optionale Felder werden von Knoten gesetzt."""

    kontext: Context
    skill_results: list[SkillResult]
    gesamtstatus: str       # "ok" | "pruefen" | "fehler"
    bericht_md_pfad: str
    bericht_html_pfad: str
    fehler: str
