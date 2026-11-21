"""Skill rueckfrage-entwurf: Rückfragen-Entwurf an den Steuerberater.

Deterministischer Kern: Fasst fehler/pruefen-Befunde nach Regel als
Markdown-Liste mit einmaliger Schlussbitte je Gruppe.

LLM-Formulierung: Ein Modellaufruf für alle Gruppen. Zuordnung per Regelname
(nicht Position). Zahl-Kontrolle je Gruppe: keine Fremdzahlen, alle Pflicht-
Angaben (Beträge €, Kontonummern, Anzahlen ×) müssen vorkommen, keine
Zahlwörter. Bei Verstoß fällt nur die betroffene Gruppe auf den
deterministischen Text zurück, mit Hinweis im Befund.
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

# Ganzzahlige Ziffernfolgen: Tausenderformat (1.234,56 | 1.234) ODER
# plain (1234,56 | 1234). Keine Fragmentierung 4-stelliger Zahlen.
_ZAHL_RE = re.compile(
    r'(?<!\d)'
    r'(?:\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)'
    r'(?!\d)'
)

# Beträge direkt vor €
_BETRAG_RE = re.compile(
    r'((?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?)\s*€'
)
# Kontonummern nach "Konto" (mindestens 3-stellig)
_KONTO_RE = re.compile(r'[Kk]onto\s+(\d{3,})')
# Anzahlen (N× oder N vor überfällig/offene)
_ANZAHL_RE = re.compile(r'(\d+)\s*[×x]')
_ANZAHL2_RE = re.compile(r'(\d+)\s+überfällig', re.IGNORECASE)

# Zahlwörter, die der LLM-Text nicht enthalten darf
_ZAHLWOERTER: frozenset[str] = frozenset({
    "null", "eins",
    "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun",
    "zehn", "elf", "zwölf",
    "einmal", "zweimal", "dreimal", "viermal", "fünfmal",
    "sechsmal", "siebenmal", "achtmal", "neunmal", "zehnmal",
})


# ---------------------------------------------------------------------------
# Pydantic-Modelle für LLM-Antwort
# ---------------------------------------------------------------------------

class _Gruppe(BaseModel):
    thema: str    # Skill-ID (exakt wie angegeben), max. 60 Zeichen
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
# Zahlen-Hilfsfunktionen
# ---------------------------------------------------------------------------

def _normalize_zahl(s: str) -> str:
    """Normalisiert eine deutsche Zahl: Tausenderpunkte entfernen, Komma → Punkt."""
    result = re.sub(r'\.(?=\d{3})', '', s)
    return result.replace(',', '.')


def _zahlen_norm_aus_text(text: str) -> frozenset[str]:
    return frozenset(_normalize_zahl(m.group(0)) for m in _ZAHL_RE.finditer(text))


def _extrahiere_zahlen_norm(findings: list[Finding]) -> frozenset[str]:
    zahlen: set[str] = set()
    for f in findings:
        for src in [f.title, f.detail]:
            for m in _ZAHL_RE.finditer(src):
                zahlen.add(_normalize_zahl(m.group(0)))
    return frozenset(zahlen)


def _pflicht_zahlen_norm(findings: list[Finding]) -> frozenset[str]:
    """Beträge (€), Kontonummern (≥3-stellig) und Anzahlen (N×) aus den Befunden."""
    zahlen: set[str] = set()
    for f in findings:
        for src in [f.title, f.detail]:
            for m in _BETRAG_RE.finditer(src):
                zahlen.add(_normalize_zahl(m.group(1)))
            for m in _KONTO_RE.finditer(src):
                zahlen.add(m.group(1))
            for m in _ANZAHL_RE.finditer(src):
                zahlen.add(m.group(1))
            for m in _ANZAHL2_RE.finditer(src):
                zahlen.add(m.group(1))
    return frozenset(zahlen)


def _periode_zahlen_norm(auswertung: Auswertung) -> frozenset[str]:
    return frozenset({
        str(auswertung.year),
        str(auswertung.month),
        f"{auswertung.month:02d}",
    })


def _enthaelt_zahlwort(text: str) -> bool:
    words = re.findall(r'\b\w+\b', text.lower())
    return any(w in _ZAHLWOERTER for w in words)


def _pruefe_gruppe(
    text: str,
    gruppe: list[Finding],
    auswertung: Auswertung,
) -> tuple[bool, str]:
    """Prüft LLM-Text für eine Gruppe: keine Zahlwörter, keine Fremdzahlen, vollständig.

    Rückgabe: (ok, grund). Grund ist leer wenn ok.
    Vollständigkeit: alle Beträge (€), Kontonummern und Anzahlen aus den
    Befunden müssen (normalisiert) im LLM-Text vorkommen.
    """
    quell_norm = _extrahiere_zahlen_norm(gruppe)
    pflicht_norm = _pflicht_zahlen_norm(gruppe)
    erlaubt = quell_norm | _periode_zahlen_norm(auswertung)
    llm_norm = _zahlen_norm_aus_text(text)
    periode = _periode_zahlen_norm(auswertung)

    if _enthaelt_zahlwort(text):
        return False, "Zahlwort im Text"

    for n in llm_norm:
        if n not in erlaubt:
            return False, f"Fremdzahl: {n}"

    for n in pflicht_norm:
        if n not in llm_norm and n not in periode:
            return False, f"Pflichtzahl fehlt: {n}"

    return True, ""


# ---------------------------------------------------------------------------
# Deterministischer Kern
# ---------------------------------------------------------------------------

def _entwurf_deterministisch_gruppe(
    rule: str,
    gruppe: list[Finding],
    *,
    hinweis: str = "",
) -> Finding:
    """Deterministisches Finding für eine einzelne Gruppe."""
    n = len(gruppe)
    zeilen = [f"- Zu {rule}: {f.title}" for f in gruppe]
    teile = ["\n".join(zeilen), "Bitte prüfen und den Sachverhalt mitteilen."]
    if hinweis:
        teile.append(f"({hinweis})")
    return Finding(
        rule=SKILL_ID,
        severity="info",
        title=f"Rückfrage: {rule} ({n} Befund{'e' if n != 1 else ''})",
        detail="\n".join(teile),
    )


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

    return [
        _entwurf_deterministisch_gruppe(rule, gruppe, hinweis=hinweis)
        for rule, gruppe in gruppen.items()
    ]


# ---------------------------------------------------------------------------
# Prompt-Bau
# ---------------------------------------------------------------------------

def _baue_prompt(gruppen_dict: dict[str, list[Finding]], periode_str: str) -> str:
    """Baut den Prompt für den LLM-Aufruf (ein Aufruf für alle Gruppen)."""
    gruppen_teile: list[str] = []
    for rule, gruppe in gruppen_dict.items():
        n = len(gruppe)
        befunde_zeilen = [f"  Befund: {f.title}" for f in gruppe]
        gruppen_teile.append(
            f'Gruppe "{rule}" ({n} Befund{"e" if n != 1 else ""}):\n'
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

    # Zuordnung per Regelname (nicht Position); erste Nennung gewinnt bei Duplikaten
    llm_map: dict[str, _Gruppe] = {}
    for g in antwort.gruppen:
        thema = g.thema.strip()
        if thema not in llm_map:
            llm_map[thema] = g

    result: list[Finding] = []
    for rule, gruppe in gruppen_dict.items():
        llm_gruppe = llm_map.get(rule)
        if llm_gruppe is None:
            log.debug("rueckfrage-entwurf: Gruppe %s fehlt in LLM-Antwort – Fallback", rule)
            result.append(_entwurf_deterministisch_gruppe(rule, gruppe))
            continue

        ok, hinweis = _pruefe_gruppe(llm_gruppe.text, gruppe, ctx.auswertung)
        if not ok:
            log.debug("rueckfrage-entwurf: Gruppe %s: %s – Fallback", rule, hinweis)
            result.append(_entwurf_deterministisch_gruppe(rule, gruppe, hinweis=hinweis))
            continue

        n = len(gruppe)
        result.append(Finding(
            rule=SKILL_ID,
            severity="info",
            title=f"Rückfrage: {llm_gruppe.thema} ({n} Befund{'e' if n != 1 else ''})",
            detail=llm_gruppe.text,
        ))

    return result
