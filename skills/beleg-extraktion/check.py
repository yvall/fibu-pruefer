"""Skill beleg-extraktion: LLM-gestützte Extraktion von Betrag/Datum/Nummer
aus Belegen, die der deterministische Parser nicht lesen konnte.

Kerninvariante (CLAUDE.md): Zahlen und Prüflogik bleiben deterministischer Code.
LLMs lesen und ordnen zu; ihre Ausgabe wird gegen ein Pydantic-Schema validiert.
Jeder extrahierte Wert muss im Originaltext vorkommen (Guard gegen Halluzination).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel, ValidationError

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Ref
from fibu.llm import LlmClient

SKILL_ID = "beleg-extraktion"
log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "extraktion.md").read_text(
    encoding="utf-8"
)
_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "betrag": {"type": "string"},
        "datum": {"type": "string"},
        "nummer": {"type": "string"},
    },
    "required": ["betrag", "datum", "nummer"],
    "additionalProperties": False,
}


class _LlmAntwort(BaseModel):
    betrag: str = ""
    datum: str = ""
    nummer: str = ""


def _prompt_rendern(belegtext: str) -> str:
    return _PROMPT_TEMPLATE.replace("{{ belegtext }}", belegtext)


def _wert_in_text(wert: str, text: str) -> bool:
    """Guard: prüft ob wert (in verschiedenen normierten Schreibweisen) im Text steht."""
    if not wert.strip():
        return True  # Leerer Wert benötigt keinen Guard
    # Direkte Suche
    if wert.strip() in text:
        return True
    # Whitespace-komprimiert
    tc = re.sub(r"\s", "", text)
    wc = re.sub(r"\s", "", wert)
    if wc in tc:
        return True
    # Betrag DE→EN: "1.234,56" → "1234.56"
    de_en = re.sub(r"\.(?=\d{3})", "", wc).replace(",", ".")
    if de_en != wc and de_en in tc:
        return True
    # Betrag EN→DE: "1,234.56" → "1234,56"
    en_de = re.sub(r",(?=\d{3})", "", wc).replace(".", ",")
    if en_de != wc and en_de in tc:
        return True
    # Ziffern-Fallback für Belegnummern/Datumsfelder mit Trennzeichen (≥5 Ziffern)
    digits_w = re.sub(r"\D", "", wc)
    if len(digits_w) >= 5:
        digits_t = re.sub(r"\D", "", tc)
        if digits_w in digits_t:
            return True
    return False


def _parse_llm_antwort(roh: str) -> _LlmAntwort | None:
    """Structured-Output-Parse mit json.loads-Fallback (E8)."""
    # Versuch 1: direktes Pydantic-Parsing
    try:
        return _LlmAntwort.model_validate_json(roh)
    except (ValueError, ValidationError):
        pass
    # Versuch 2: json.loads-Fallback (z. B. wenn Modell Erklärtext voranstellt)
    try:
        parsed = json.loads(roh)
        return _LlmAntwort.model_validate(parsed)
    except (ValueError, ValidationError, json.JSONDecodeError):
        pass
    # Versuch 3: erstes JSON-Objekt aus dem Text extrahieren
    m = re.search(r"\{[^{}]+\}", roh, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(0))
            return _LlmAntwort.model_validate(parsed)
        except (ValueError, ValidationError, json.JSONDecodeError):
            pass
    return None


def _extrahiere(beleg_rel: str, text: str, llm: LlmClient) -> list[Finding]:
    """Ruft LLM für einen Beleg auf und gibt Findings zurück."""
    modell = llm.modell_fuer(SKILL_ID)
    prompt = _prompt_rendern(text[:4000])  # Kontext-Länge begrenzen

    roh_antwort = llm.generiere(prompt, json_schema=_JSON_SCHEMA, modell=modell)

    if roh_antwort is None:
        log.debug("Kein LLM-Response für Beleg %s", beleg_rel)
        return [
            Finding(
                rule=SKILL_ID,
                severity="pruefen",
                title=f"LLM-Extraktion fehlgeschlagen: {beleg_rel}",
                detail="Das Sprachmodell hat keine Antwort geliefert.",
                refs=[Ref(art="beleg", id=beleg_rel)],
            )
        ]

    antwort = _parse_llm_antwort(roh_antwort)
    if antwort is None:
        log.debug(
            "Pydantic-Validierungsfehler für %s | Roh: %r", beleg_rel, roh_antwort[:200]
        )
        return [
            Finding(
                rule=SKILL_ID,
                severity="pruefen",
                title=f"LLM-Extraktion fehlgeschlagen: {beleg_rel}",
                detail=f"LLM-Antwort nicht auswertbar: {roh_antwort[:100]!r}",
                refs=[Ref(art="beleg", id=beleg_rel)],
            )
        ]

    # Guard: jeder nicht-leere extrahierte Wert muss im Originaltext vorkommen
    guard_fehler: list[str] = []
    for feldname, wert in [
        ("betrag", antwort.betrag),
        ("datum", antwort.datum),
        ("nummer", antwort.nummer),
    ]:
        if wert and not _wert_in_text(wert, text):
            guard_fehler.append(f"{feldname}={wert!r}")

    if guard_fehler:
        return [
            Finding(
                rule=SKILL_ID,
                severity="pruefen",
                title=f"Extrahierter Wert nicht im Belegtext: {beleg_rel}",
                detail=(
                    f"Guard fehlgeschlagen – folgende Felder kommen im Text nicht vor: "
                    f"{', '.join(guard_fehler)}"
                ),
                refs=[Ref(art="beleg", id=beleg_rel)],
            )
        ]

    if not any([antwort.betrag, antwort.datum, antwort.nummer]):
        return [
            Finding(
                rule=SKILL_ID,
                severity="pruefen",
                title=f"Keine Felder extrahiert: {beleg_rel}",
                detail="Das Sprachmodell hat keine Felder erkannt.",
                refs=[Ref(art="beleg", id=beleg_rel)],
            )
        ]

    teile = []
    if antwort.betrag:
        teile.append(f"Betrag: {antwort.betrag}")
    if antwort.datum:
        teile.append(f"Datum: {antwort.datum}")
    if antwort.nummer:
        teile.append(f"Nr.: {antwort.nummer}")

    return [
        Finding(
            rule=SKILL_ID,
            severity="info",
            title=f"Felder extrahiert: {beleg_rel}",
            detail=", ".join(teile),
            refs=[Ref(art="beleg", id=beleg_rel)],
        )
    ]


def run(ctx: Context, llm: LlmClient) -> list[Finding]:
    """Extrahiert Felder aus Belegen ohne erkannte Beträge (deterministische Zuordnung fehlt)."""
    unlesbar = [b for b in ctx.belege if not b.alle and b.kind != "storno"]
    findings: list[Finding] = []
    for beleg in unlesbar:
        if not beleg.text.strip():
            continue  # Kein OCR-Text – nicht ans LLM schicken
        findings.extend(_extrahiere(beleg.rel, beleg.text, llm))
    return findings
