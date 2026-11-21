from __future__ import annotations

from typing import TypedDict

from fibu.contracts import Entscheidung
from fibu.skills_runtime import SkillResult


class _PruefStateBasis(TypedDict):
    """Pflichtfelder – müssen im Initialzustand gesetzt sein."""

    ordner: str
    skills_dir: str
    config: dict[str, object]
    lauf_id: str
    mit_mail: bool


class PruefState(_PruefStateBasis, total=False):
    """Vollständiger Graph-State; optionale Felder werden von Knoten gesetzt.

    Kein Context-Objekt im State (E3): wird über LaufStore nachgeladen.
    Decimal- und str-Werte sind SqliteSaver-serialisierbar.
    """

    skill_results: list[SkillResult]
    gesamtstatus: str       # "ok" | "pruefen" | "fehler"
    bericht_md_pfad: str
    bericht_html_pfad: str
    entscheidung: Entscheidung   # nach warte_auf_freigabe (nur mit --mail)
    versand_ok: bool             # True nach erfolgreichem Versand (oder Trockenlauf)
    fehler: str
