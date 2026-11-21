"""Skill rueckfrage-entwurf: Deterministischer Rückfragen-Entwurf an den Steuerberater.

Liest alle Befunde mit severity in ("fehler", "pruefen") aus den Vorgängerskills,
gruppiert sie nach Regel (Skill-ID) und erzeugt je Gruppe ein info-Finding.
Zahlen und Beträge kommen ausschließlich aus den Finding-Feldern – keine eigene Berechnung.
"""
from __future__ import annotations

from fibu.contracts import Context, Finding
from fibu.llm import LlmClient

SKILL_ID = "rueckfrage-entwurf"


def _entwurf_deterministisch(findings: list[Finding]) -> list[Finding]:
    """Erzeugt pro Skill-Gruppe ein info-Finding mit Rückfragetext."""
    relevant = [
        f for f in findings
        if f.severity in ("fehler", "pruefen") and f.rule != SKILL_ID
    ]
    if not relevant:
        return []

    gruppen: dict[str, list[Finding]] = {}
    for f in relevant:
        gruppen.setdefault(f.rule, []).append(f)

    result: list[Finding] = []
    for rule, gruppe in gruppen.items():
        n = len(gruppe)
        zeilen = [
            f"Zu {rule}: {f.title} – bitte prüfen und den Sachverhalt mitteilen."
            for f in gruppe
        ]
        result.append(Finding(
            rule=SKILL_ID,
            severity="info",
            title=f"Rückfrage: {rule} ({n} Befund{'e' if n != 1 else ''})",
            detail="\n".join(zeilen),
        ))

    return result


def run(ctx: Context, llm: LlmClient) -> list[Finding]:
    """Erzeugt einen Rückfragen-Entwurf aus den Befunden der Vorgängerskills."""
    return _entwurf_deterministisch(ctx.befunde)
