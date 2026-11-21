"""Skill rueckfrage-entwurf: Rückfragen-Entwurf an den Steuerberater.

Deterministischer Kern: Fasst fehler/pruefen-Befunde nach Regel
als Markdown-Liste mit einer gemeinsamen Schlussbitte je Gruppe.

LLM-Formulierung: Formuliert den Fließtext über ein Sprachmodell (ein Aufruf
pro Lauf). _pruefe_zahlen_konsistenz() stellt sicher, dass keine Zahlen
hinzuerfunden werden; bei Verstoß oder Parse-Fehler → deterministischer Fallback.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from fibu.contracts import Auswertung, Context, Finding
from fibu.llm import LlmClient

SKILL_ID = "rueckfrage-entwurf"
log = logging.getLogger(__name__)

_MON = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
        "August", "September", "Oktober", "November", "Dezember"]

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "rueckfrage.md").read_text(
    encoding="utf-8"
)

# Regex für deutsche Zahlenformate (Plan §3)
_ZAHL_RE = re.compile(r"\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?")


# ---------------------------------------------------------------------------
# Pydantic-Modelle für LLM-Antwort
# ---------------------------------------------------------------------------

class _Gruppe(BaseModel):
    thema: str    # Skill-ID oder Thema, max. 60 Zeichen
    text: str     # Rückfragetext, max. 500 Zeichen, kein Markdown


class _LlmAntwort(BaseModel):
    gruppen: list[_Gruppe]


_LlmAntwort.model_rebuild()

_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "gruppen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "thema": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["thema", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["gruppen"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Zahlen-Normalisierung und Konsistenz-Prüfung
# ---------------------------------------------------------------------------

def _normalize_zahl(s: str) -> str:
    """Normalisiert eine deutsche Zahl: Tausenderpunkte entfernen, Komma → Punkt."""
    result = re.sub(r'\.(?=\d{3})', '', s)
    return result.replace(',', '.')


def _extrahiere_zahlen_norm(findings: list[Finding]) -> frozenset[str]:
    """Normalisiert alle Ziffernfolgen aus title und detail der Findings."""
    zahlen: set[str] = set()
    for f in findings:
        for src in [f.title, f.detail]:
            for m in _ZAHL_RE.finditer(src):
                zahlen.add(_normalize_zahl(m.group(0)))
    return frozenset(zahlen)


def _pruefe_zahlen_konsistenz(
    text: str,
    quellzahlen_norm: frozenset[str],
    auswertung: Auswertung,
) -> bool:
    """True wenn alle Ziffernfolgen im text aus den Quellen oder der Periode stammen.

    Jahr und Monat werden mit demselben Regex fragmentiert (z. B. "2024" → "202" + "4"),
    damit sie konsistent mit der Extraktion aus dem LLM-Text verglichen werden können.
    """
    erlaubt = set(quellzahlen_norm)
    for spez in [str(auswertung.year), str(auswertung.month), f"{auswertung.month:02d}"]:
        for m in _ZAHL_RE.finditer(spez):
            erlaubt.add(_normalize_zahl(m.group(0)))

    for m in _ZAHL_RE.finditer(text):
        norm = _normalize_zahl(m.group(0))
        if norm not in erlaubt:
            log.debug("Zahl-Kontrolle: unbekannte Zahl %r in LLM-Antwort", m.group(0))
            return False
    return True


# ---------------------------------------------------------------------------
# Deterministischer Kern
# ---------------------------------------------------------------------------

def _entwurf_deterministisch(
    findings: list[Finding],
    *,
    hinweis: str = "",
) -> list[Finding]:
    """Erzeugt pro Skill-Gruppe ein info-Finding als Markdown-Liste."""
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
        zeilen = [f"- Zu {rule}: {f.title}" for f in gruppe]
        teile = ["\n".join(zeilen), "Bitte prüfen und den Sachverhalt mitteilen."]
        if hinweis:
            teile.append(f"({hinweis})")
        result.append(Finding(
            rule=SKILL_ID,
            severity="info",
            title=f"Rückfrage: {rule} ({n} Befund{'e' if n != 1 else ''})",
            detail="\n".join(teile),
        ))

    return result


# ---------------------------------------------------------------------------
# Prompt-Bau
# ---------------------------------------------------------------------------

def _baue_prompt(gruppen_dict: dict[str, list[Finding]], periode_str: str) -> str:
    """Baut den Prompt für den LLM-Aufruf (ein Aufruf für alle Gruppen)."""
    gruppen_teile: list[str] = []
    for i, (rule, gruppe) in enumerate(gruppen_dict.items()):
        n = len(gruppe)
        befunde_zeilen = [f"  Befund: {f.title}" for f in gruppe]
        gruppen_teile.append(
            f'Gruppe {i} "{rule}" ({n} Befund{"e" if n != 1 else ""}):\n'
            + "\n".join(befunde_zeilen)
        )
    gruppen_text = "\n\n".join(gruppen_teile)
    return (
        _PROMPT_TEMPLATE
        .replace("{{ periode }}", periode_str)
        .replace("{{ gruppen }}", gruppen_text)
    )


# ---------------------------------------------------------------------------
# LLM-Antwort-Parsing
# ---------------------------------------------------------------------------

def _parse_llm_antwort(roh: str) -> _LlmAntwort | None:
    try:
        return _LlmAntwort.model_validate_json(roh)
    except (ValueError, ValidationError):
        pass
    try:
        return _LlmAntwort.model_validate(json.loads(roh))
    except (ValueError, ValidationError, json.JSONDecodeError):
        pass
    # JSON in Fließtext eingebettet
    m = re.search(r'\{.*"gruppen".*\}', roh, re.DOTALL)
    if m:
        try:
            return _LlmAntwort.model_validate(json.loads(m.group(0)))
        except (ValueError, ValidationError, json.JSONDecodeError):
            pass
    return None


# ---------------------------------------------------------------------------
# Skill-Einstiegspunkt
# ---------------------------------------------------------------------------

def run(ctx: Context, llm: LlmClient) -> list[Finding]:
    """Erzeugt einen Rückfragen-Entwurf aus den Befunden der Vorgängerskills."""
    from fibu.llm.null import NullLlmClient

    if isinstance(llm, NullLlmClient):
        return _entwurf_deterministisch(ctx.befunde)

    relevant = [
        f for f in ctx.befunde
        if f.severity in ("fehler", "pruefen") and f.rule != SKILL_ID
    ]
    if not relevant:
        return []

    gruppen_dict: dict[str, list[Finding]] = {}
    for f in relevant:
        gruppen_dict.setdefault(f.rule, []).append(f)

    quellzahlen_norm = _extrahiere_zahlen_norm(relevant)
    periode_str = f"{_MON[ctx.auswertung.month]} {ctx.auswertung.year}"
    prompt = _baue_prompt(gruppen_dict, periode_str)

    modell = llm.modell_fuer(SKILL_ID)
    roh = llm.generiere(prompt, json_schema=_JSON_SCHEMA, modell=modell)

    if roh is None:
        log.debug("rueckfrage-entwurf: kein LLM-Response – deterministischer Fallback")
        return _entwurf_deterministisch(ctx.befunde)

    antwort = _parse_llm_antwort(roh)
    if antwort is None:
        log.debug("rueckfrage-entwurf: Parse-Fehler – deterministischer Fallback")
        return _entwurf_deterministisch(ctx.befunde)

    # Zahl-Kontrolle über gesamte LLM-Ausgabe
    gesamttext = " ".join(g.text for g in antwort.gruppen)
    if not _pruefe_zahlen_konsistenz(gesamttext, quellzahlen_norm, ctx.auswertung):
        log.debug("rueckfrage-entwurf: Zahl-Kontrolle geschlagen – Fallback")
        return _entwurf_deterministisch(ctx.befunde, hinweis="Zahlenkontrolle: Rückfall")

    # LLM-Gruppen auf Quellgruppen abbilden (positionsbasiert)
    gruppen_liste = list(gruppen_dict.items())
    result: list[Finding] = []
    for i, llm_gruppe in enumerate(antwort.gruppen):
        if i >= len(gruppen_liste):
            break
        rule, gruppe = gruppen_liste[i]
        n = len(gruppe)
        result.append(Finding(
            rule=SKILL_ID,
            severity="info",
            title=f"Rückfrage: {llm_gruppe.thema} ({n} Befund{'e' if n != 1 else ''})",
            detail=llm_gruppe.text,
        ))

    # Fehlende Gruppen deterministisch ergänzen
    for rule, gruppe in gruppen_liste[len(antwort.gruppen):]:
        n = len(gruppe)
        zeilen = [f"- Zu {rule}: {f.title}" for f in gruppe]
        result.append(Finding(
            rule=SKILL_ID,
            severity="info",
            title=f"Rückfrage: {rule} ({n} Befund{'e' if n != 1 else ''})",
            detail="\n".join(zeilen) + "\nBitte prüfen und den Sachverhalt mitteilen.",
        ))

    return result
