"""Skill beleg-extraktion: LLM-gestützte Extraktion von Betrag/Datum/Nummer
aus Belegen, die der deterministische Parser nicht lesen konnte.

Kerninvariante (CLAUDE.md): Zahlen und Prüflogik bleiben deterministischer Code.
LLMs lesen und ordnen zu; ihre Ausgabe wird gegen ein Pydantic-Schema validiert.
Jeder extrahierte Wert muss im Originaltext vorkommen (Guard gegen Halluzination).
Brutto wird nur übernommen wenn netto + ust = brutto (±Toleranz) und alle drei
Felder vorhanden sind. Ist nur ein Betrag vorhanden, wird er nicht als Brutto gewertet.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ValidationError

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Ref
from fibu.llm import LlmClient

SKILL_ID = "beleg-extraktion"
log = logging.getLogger(__name__)

_DEFAULT_TOLERANZ = Decimal("0.02")

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "extraktion.md").read_text(
    encoding="utf-8"
)
_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "brutto": {"type": "string"},
        "netto": {"type": "string"},
        "ust": {"type": "string"},
        "datum": {"type": "string"},
        "nummer": {"type": "string"},
    },
    "required": ["brutto", "netto", "ust", "datum", "nummer"],
    "additionalProperties": False,
}


class _LlmAntwort(BaseModel):
    brutto: str = ""
    netto: str = ""
    ust: str = ""
    datum: str = ""
    nummer: str = ""


def _prompt_rendern(belegtext: str) -> str:
    return _PROMPT_TEMPLATE.replace("{{ belegtext }}", belegtext)


def _parse_betrag_de(s: str) -> Decimal | None:
    """Parst deutschen Betragsstring → Decimal. '1.234,56' → Decimal('1234.56')."""
    if not s.strip():
        return None
    # Tausender-Punkte entfernen (Punkt gefolgt von genau 3 Ziffern), dann Komma → Punkt
    cleaned = re.sub(r"\.(?=\d{3})", "", s.strip()).replace(",", ".")
    try:
        return Decimal(cleaned)
    except Exception:  # noqa: BLE001
        return None


def _pruefe_brutto(
    netto_str: str, ust_str: str, brutto_str: str, toleranz: Decimal
) -> Decimal | None:
    """Gibt brutto als Decimal zurück wenn netto + ust = brutto (±toleranz), sonst None.

    Wenn nicht alle drei Felder vorhanden sind (einschl. 'nur brutto' ohne netto/ust),
    wird None zurückgegeben – ein einzelner Betrag wird nicht als brutto gewertet.
    """
    netto = _parse_betrag_de(netto_str)
    ust = _parse_betrag_de(ust_str)
    brutto = _parse_betrag_de(brutto_str)
    if netto is None or ust is None or brutto is None:
        return None
    if abs(netto + ust - brutto) <= toleranz:
        return brutto
    return None


def _wert_in_text(wert: str, text: str) -> bool:
    """Guard: prüft ob wert (in verschiedenen normierten Schreibweisen) im Text steht."""
    if not wert.strip():
        return True
    if wert.strip() in text:
        return True
    tc = re.sub(r"\s", "", text)
    wc = re.sub(r"\s", "", wert)
    if wc in tc:
        return True
    de_en = re.sub(r"\.(?=\d{3})", "", wc).replace(",", ".")
    if de_en != wc and de_en in tc:
        return True
    en_de = re.sub(r",(?=\d{3})", "", wc).replace(".", ",")
    if en_de != wc and en_de in tc:
        return True
    digits_w = re.sub(r"\D", "", wc)
    if len(digits_w) >= 5:
        digits_t = re.sub(r"\D", "", tc)
        if digits_w in digits_t:
            return True
    return False


def _parse_llm_antwort(roh: str) -> _LlmAntwort | None:
    """Structured-Output-Parse mit json.loads-Fallback (E8)."""
    try:
        return _LlmAntwort.model_validate_json(roh)
    except (ValueError, ValidationError):
        pass
    try:
        parsed = json.loads(roh)
        return _LlmAntwort.model_validate(parsed)
    except (ValueError, ValidationError, json.JSONDecodeError):
        pass
    m = re.search(r"\{[^{}]+\}", roh, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(0))
            return _LlmAntwort.model_validate(parsed)
        except (ValueError, ValidationError, json.JSONDecodeError):
            pass
    return None


def _extrahiere(
    beleg_rel: str,
    text: str,
    llm: LlmClient,
    toleranz: Decimal = _DEFAULT_TOLERANZ,
) -> list[Finding]:
    """Ruft LLM für einen Beleg auf und gibt Findings zurück."""
    modell = llm.modell_fuer(SKILL_ID)
    prompt = _prompt_rendern(text[:4000])

    roh_antwort = llm.generiere(prompt, json_schema=_JSON_SCHEMA, modell=modell)

    if roh_antwort is None:
        log.debug("Kein LLM-Response für Beleg %s", beleg_rel)
        return [Finding(
            rule=SKILL_ID, severity="pruefen",
            title=f"LLM-Extraktion fehlgeschlagen: {beleg_rel}",
            detail="Das Sprachmodell hat keine Antwort geliefert.",
            refs=[Ref(art="beleg", id=beleg_rel)],
        )]

    antwort = _parse_llm_antwort(roh_antwort)
    if antwort is None:
        log.debug("Pydantic-Fehler für %s | Roh: %r", beleg_rel, roh_antwort[:200])
        return [Finding(
            rule=SKILL_ID, severity="pruefen",
            title=f"LLM-Extraktion fehlgeschlagen: {beleg_rel}",
            detail=f"LLM-Antwort nicht auswertbar: {roh_antwort[:100]!r}",
            refs=[Ref(art="beleg", id=beleg_rel)],
        )]

    # Guard: jeder nicht-leere Wert muss im Originaltext vorkommen
    guard_fehler: list[str] = []
    for feldname, wert in [
        ("brutto", antwort.brutto),
        ("netto", antwort.netto),
        ("ust", antwort.ust),
        ("datum", antwort.datum),
        ("nummer", antwort.nummer),
    ]:
        if wert and not _wert_in_text(wert, text):
            guard_fehler.append(f"{feldname}={wert!r}")

    if guard_fehler:
        return [Finding(
            rule=SKILL_ID, severity="pruefen",
            title=f"Extrahierter Wert nicht im Belegtext: {beleg_rel}",
            detail=f"Guard fehlgeschlagen – folgende Felder kommen im Text nicht vor: {', '.join(guard_fehler)}",
            refs=[Ref(art="beleg", id=beleg_rel)],
        )]

    # Arithmetik-Prüfung: netto + ust = brutto (±Toleranz)
    brutto_decimal = _pruefe_brutto(antwort.netto, antwort.ust, antwort.brutto, toleranz)
    hat_betragsfelder = any([antwort.netto, antwort.ust, antwort.brutto])

    if brutto_decimal is not None:
        # Brutto arithmetisch bestätigt
        teile = [f"Brutto: {antwort.brutto}"]
        if antwort.datum:
            teile.append(f"Datum: {antwort.datum}")
        if antwort.nummer:
            teile.append(f"Nr.: {antwort.nummer}")
        return [Finding(
            rule=SKILL_ID, severity="info",
            title=f"Felder extrahiert: {beleg_rel}",
            detail=", ".join(teile),
            refs=[Ref(art="beleg", id=beleg_rel)],
        )]

    if hat_betragsfelder:
        # Betragsfelder vorhanden, aber Prüfung nicht bestanden
        felder_info = []
        if antwort.netto:
            felder_info.append(f"Netto: {antwort.netto}")
        if antwort.ust:
            felder_info.append(f"USt: {antwort.ust}")
        if antwort.brutto:
            felder_info.append(f"Brutto: {antwort.brutto}")

        alle_drei = all([antwort.netto, antwort.ust, antwort.brutto])
        if alle_drei:
            n = _parse_betrag_de(antwort.netto)
            u = _parse_betrag_de(antwort.ust)
            b = _parse_betrag_de(antwort.brutto)
            diff = abs(n + u - b) if (n and u and b) else Decimal(0)  # type: ignore[operator]
            grund = f"Arithmetik: {antwort.netto} + {antwort.ust} ≠ {antwort.brutto} (Diff. {diff})"
        else:
            grund = "nicht alle Betragsfelder vorhanden"

        detail = f"Betrag nicht eindeutig ({grund}): {', '.join(felder_info)}"
        zusatz = []
        if antwort.datum:
            zusatz.append(f"Datum: {antwort.datum}")
        if antwort.nummer:
            zusatz.append(f"Nr.: {antwort.nummer}")
        if zusatz:
            detail += "; " + ", ".join(zusatz)

        return [Finding(
            rule=SKILL_ID, severity="pruefen",
            title=f"Betrag nicht eindeutig: {beleg_rel}",
            detail=detail,
            refs=[Ref(art="beleg", id=beleg_rel)],
        )]

    # Kein Betrag, aber möglicherweise Datum/Nummer
    teile_rest = []
    if antwort.datum:
        teile_rest.append(f"Datum: {antwort.datum}")
    if antwort.nummer:
        teile_rest.append(f"Nr.: {antwort.nummer}")

    if teile_rest:
        return [Finding(
            rule=SKILL_ID, severity="info",
            title=f"Felder extrahiert (kein Betrag): {beleg_rel}",
            detail=", ".join(teile_rest),
            refs=[Ref(art="beleg", id=beleg_rel)],
        )]

    return [Finding(
        rule=SKILL_ID, severity="pruefen",
        title=f"Keine Felder extrahiert: {beleg_rel}",
        detail="Das Sprachmodell hat keine Felder erkannt.",
        refs=[Ref(art="beleg", id=beleg_rel)],
    )]


def run(ctx: Context, llm: LlmClient) -> list[Finding]:
    """Extrahiert Felder aus Belegen ohne erkannte Beträge (deterministische Zuordnung fehlt)."""
    raw = ctx.config.get("toleranz_betrag", "0.02")
    try:
        toleranz = Decimal(str(raw))
    except Exception:  # noqa: BLE001
        toleranz = _DEFAULT_TOLERANZ

    unlesbar = [b for b in ctx.belege if not b.alle and b.kind != "storno"]
    findings: list[Finding] = []
    for beleg in unlesbar:
        if not beleg.text.strip():
            continue
        findings.extend(_extrahiere(beleg.rel, beleg.text, llm, toleranz))
    return findings
