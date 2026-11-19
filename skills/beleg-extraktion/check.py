"""Skill beleg-extraktion: LLM-gestützte Extraktion von Betrag/Datum/Nummer
aus Belegen, die der deterministische Parser nicht lesen konnte.

Design (überarbeitete Fassung):
- Python extrahiert alle Kandidaten (Beträge, Daten, Nummern) aus dem Text.
  Das LLM wählt nur den Index des passenden Kandidaten, keinen Freitext.
  Damit ist jeder extrahierte Wert per Konstruktion im Belegtext vorhanden.
- Guard entfällt auf Feldebene: ein ungültiger Index wird verworfen,
  die anderen Felder bleiben erhalten.
- USt optional: Weist der Beleg keine USt aus, wird Brutto direkt akzeptiert;
  "keine Umsatzsteuer" ist kein Fehler (Auslandsbeleg, Reverse Charge, §4 UStG).
- Arithmetik-Prüfung nur wenn Netto + USt + Brutto alle ausgewählt sind.
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
_DEFAULT_KOPF_LAENGE = 600
_DEFAULT_SUMMEN_LAENGE = 400

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "extraktion.md").read_text(
    encoding="utf-8"
)

# ---------------------------------------------------------------------------
# JSON-Schema für LLM-Antwort (Index-basiert)
# ---------------------------------------------------------------------------

_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "brutto_idx": {"type": ["integer", "null"]},
        "netto_idx":  {"type": ["integer", "null"]},
        "ust_idx":    {"type": ["integer", "null"]},
        "datum_idx":  {"type": ["integer", "null"]},
        "nummer_idx": {"type": ["integer", "null"]},
    },
    "required": ["brutto_idx", "netto_idx", "ust_idx", "datum_idx", "nummer_idx"],
    "additionalProperties": False,
}


class _LlmAntwort(BaseModel):
    brutto_idx: int | None = None
    netto_idx:  int | None = None
    ust_idx:    int | None = None
    datum_idx:  int | None = None
    nummer_idx: int | None = None


# ---------------------------------------------------------------------------
# Deutsche/englische Monatsnamen
# ---------------------------------------------------------------------------

_MONATE_DE: dict[str, int] = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}
_MONATE_EN: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# ---------------------------------------------------------------------------
# Regex-Muster
# ---------------------------------------------------------------------------

# DE-Betrag: "1.234,56" oder "24,00" (genau 2 Nachkommastellen)
_AMT_DE_RE = re.compile(r"(?<![.\d,\-])(\d{1,3}(?:\.\d{3})*,\d{2})(?![,\d])")
# EN-Betrag: "1,234.56" oder "90.13" (genau 2 Nachkommastellen, kein IP-Adress-Muster)
_AMT_EN_RE = re.compile(r"(?<![.,\d\-])(\d{1,3}(?:,\d{3})*\.\d{2})(?![.,\d])")

# Summen-Schlüsselwörter für Textauswahl
_SUMMEN_KW_RE = re.compile(
    r"\b(?:summe|gesamt|brutto|netto|total|zu zahlen|zahlbetrag|amount due|"
    r"endbetrag|rechnungsbetrag|gesamtbetrag|subtotal|invoice total|montant ttc|"
    r"rechnungsbetrag|zu zahlend|gesamtpreis|bruttobetrag)\b",
    re.IGNORECASE,
)

# Nummern nach Schlüsselwörtern
# Suffixe sind bewusst NICHT optional: "Rechnungsdatum" darf nicht matchen.
# Kein Leerzeichen im Capture-Ausdruck: verhindert Multi-Wort-Captures.
_NR_KW_RE = re.compile(
    r"(?:"
    r"Rechnungs(?:nummer|nr\.?)"                      # Rechnungsnummer, Rechnungsnr.
    r"|Invoice\s*(?:number|no\.?|nr\.?|#)"            # Invoice number / no. / nr. / #
    r"|Receipt\s*(?:no\.?|nr\.?|#)"                   # Receipt no. / nr. / #
    r"|Beleg(?:nummer|-?Nr\.?)"                        # Belegnummer, Beleg-Nr.
    r"|Gutschrift(?:-Nr\.?|s(?:-?Nr\.?|nummer))"       # Gutschrift-Nr., Gutschriftsnummer
    r"|Buchungsnummer"
    r"|Facture"
    r"|Nr\."                                            # Nr. (Punkt obligatorisch)
    r"|No\."                                            # No. (Punkt obligatorisch)
    r")\s*[:.\s#]*"
    r"([A-Z0-9][-A-Z0-9/_.]{2,29})",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Kandidaten-Extraktion
# ---------------------------------------------------------------------------

def _extrahiere_betraege(text: str) -> list[str]:
    """Extrahiert Betragskandidaten in DE-Format (einmalig je Wert)."""
    seen: set[str] = set()
    result: list[str] = []

    # DE: "1.234,56" oder "24,00"
    for m in _AMT_DE_RE.finditer(text):
        val = m.group(1)
        if val not in seen:
            seen.add(val)
            result.append(val)

    # EN: "90.13" oder "1,234.56" → konvertieren zu "90,13" / "1234,56"
    for m in _AMT_EN_RE.finditer(text):
        en = m.group(1)
        # Tausender-Komma entfernen, Dezimal-Punkt → Komma
        de = en.replace(",", "").replace(".", ",")
        if de not in seen:
            seen.add(de)
            result.append(de)

    return result[:20]


def _extrahiere_datumsangaben(text: str) -> list[str]:
    """Extrahiert Datumsangaben und normalisiert sie zu DD.MM.YYYY."""
    seen: set[str] = set()
    found: list[tuple[int, str]] = []  # (pos, normalized)

    def _add(pos: int, d: int, mo: int, y: str) -> None:
        if 1 <= mo <= 12 and 1 <= d <= 31:
            norm = f"{d:02d}.{mo:02d}.{y}"
            if norm not in seen:
                seen.add(norm)
                found.append((pos, norm))

    # DD.MM.YYYY
    for m in re.finditer(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", text):
        _add(m.start(), int(m.group(1)), int(m.group(2)), m.group(3))

    # MM/DD/YYYY (US)
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text):
        _add(m.start(), int(m.group(2)), int(m.group(1)), m.group(3))

    # YYYY-MM-DD (ISO)
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
        _add(m.start(), int(m.group(3)), int(m.group(2)), m.group(1))

    # Month DD, YYYY (englisch): "August 22, 2026"
    pat_en = re.compile(
        r"\b(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
        re.IGNORECASE,
    )
    for m in pat_en.finditer(text):
        mo = _MONATE_EN.get(m.group(1).lower(), 0)
        _add(m.start(), int(m.group(2)), mo, m.group(3))

    # DD. Monatsname YYYY (deutsch): "22. August 2026"
    pat_de = re.compile(
        r"\b(\d{1,2})\.\s*(Januar|Februar|März|April|Mai|Juni|Juli|August|"
        r"September|Oktober|November|Dezember)\s+(\d{4})\b",
        re.IGNORECASE,
    )
    for m in pat_de.finditer(text):
        mo = _MONATE_DE.get(m.group(2).lower(), 0)
        _add(m.start(), int(m.group(1)), mo, m.group(3))

    found.sort(key=lambda x: x[0])
    return [norm for _, norm in found[:10]]


def _extrahiere_nummern(text: str) -> list[str]:
    """Extrahiert nummernähnliche Zeichenfolgen nach Rechnungs-Schlüsselwörtern."""
    seen: set[str] = set()
    result: list[str] = []
    for m in _NR_KW_RE.finditer(text):
        val = m.group(1).strip().rstrip(".")
        if val and val not in seen and len(val) <= 30:
            seen.add(val)
            result.append(val)
    return result[:10]


def _relevanter_text(
    text: str, kopf_laenge: int, summen_laenge: int
) -> tuple[str, str]:
    """Gibt (Belegkopf, Summenblock) zurück."""
    kopf = text[:kopf_laenge]
    lines = text.splitlines()
    summen_lines: list[str] = []
    for i, line in enumerate(lines):
        if _SUMMEN_KW_RE.search(line):
            start = max(0, i - 1)
            end = min(len(lines), i + 3)
            summen_lines.extend(lines[start:end])
    summenblock = "\n".join(summen_lines)[:summen_laenge]
    return kopf, summenblock


def _baue_prompt(
    kopf: str,
    summenblock: str,
    betraege: list[str],
    datumsangaben: list[str],
    nummern: list[str],
) -> str:
    def _fmt(lst: list[str]) -> str:
        if not lst:
            return "(keine)"
        return "  ".join(f"[{i}] {v}" for i, v in enumerate(lst))

    return (
        _PROMPT_TEMPLATE
        .replace("{{ kopf }}", kopf.strip())
        .replace("{{ summenblock }}", summenblock.strip() or "(keine Summenzeilen erkannt)")
        .replace("{{ betraege }}", _fmt(betraege))
        .replace("{{ datumsangaben }}", _fmt(datumsangaben))
        .replace("{{ nummern }}", _fmt(nummern))
    )


# ---------------------------------------------------------------------------
# Arithmetik-Hilfsfunktionen (unveränd.)
# ---------------------------------------------------------------------------

def _parse_betrag_de(s: str) -> Decimal | None:
    """'1.234,56' oder '90,13' → Decimal."""
    if not s.strip():
        return None
    cleaned = re.sub(r"\.(?=\d{3})", "", s.strip()).replace(",", ".")
    try:
        return Decimal(cleaned)
    except Exception:  # noqa: BLE001
        return None


def _pruefe_brutto(
    netto_str: str, ust_str: str, brutto_str: str, toleranz: Decimal
) -> Decimal | None:
    """netto + ust = brutto (±toleranz) → brutto als Decimal, sonst None."""
    netto = _parse_betrag_de(netto_str)
    ust = _parse_betrag_de(ust_str)
    brutto = _parse_betrag_de(brutto_str)
    if netto is None or ust is None or brutto is None:
        return None
    if abs(netto + ust - brutto) <= toleranz:
        return brutto
    return None


# ---------------------------------------------------------------------------
# LLM-Antwort-Parsing (unveränd. Fallback-Kette)
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
    m = re.search(r"\{[^{}]+\}", roh, re.DOTALL)
    if m:
        try:
            return _LlmAntwort.model_validate(json.loads(m.group(0)))
        except (ValueError, ValidationError, json.JSONDecodeError):
            pass
    return None


# ---------------------------------------------------------------------------
# Guard (bleibt als Hilfsfunktion für externe Tests)
# ---------------------------------------------------------------------------

def _wert_in_text(wert: str, text: str) -> bool:
    """Prüft ob wert in normierter Form im Text steht (Legacy-Guard)."""
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


# ---------------------------------------------------------------------------
# Kern-Extraktion
# ---------------------------------------------------------------------------

def _extrahiere(
    beleg_rel: str,
    text: str,
    llm: LlmClient,
    toleranz: Decimal = _DEFAULT_TOLERANZ,
    kopf_laenge: int = _DEFAULT_KOPF_LAENGE,
    summen_laenge: int = _DEFAULT_SUMMEN_LAENGE,
) -> list[Finding]:
    """Ruft LLM mit Kandidatenliste auf; LLM gibt nur Indizes zurück."""
    # 1. Kandidaten aus Text
    betraege = _extrahiere_betraege(text)
    datumsangaben = _extrahiere_datumsangaben(text)
    nummern = _extrahiere_nummern(text)

    kopf, summenblock = _relevanter_text(text, kopf_laenge, summen_laenge)
    prompt = _baue_prompt(kopf, summenblock, betraege, datumsangaben, nummern)

    # 2. LLM-Aufruf
    modell = llm.modell_fuer(SKILL_ID)
    roh = llm.generiere(prompt, json_schema=_JSON_SCHEMA, modell=modell)

    if roh is None:
        log.debug("Kein LLM-Response für %s", beleg_rel)
        return [Finding(
            rule=SKILL_ID, severity="pruefen",
            title=f"LLM-Extraktion fehlgeschlagen: {beleg_rel}",
            detail="Kein LLM-Response.",
            refs=[Ref(art="beleg", id=beleg_rel)],
        )]

    antwort = _parse_llm_antwort(roh)
    if antwort is None:
        log.debug("Parse-Fehler für %s | Roh: %r", beleg_rel, roh[:200])
        return [Finding(
            rule=SKILL_ID, severity="pruefen",
            title=f"LLM-Extraktion fehlgeschlagen: {beleg_rel}",
            detail=f"Antwort nicht auswertbar: {roh[:100]!r}",
            refs=[Ref(art="beleg", id=beleg_rel)],
        )]

    # 3. Indizes → Werte (ungültiger Index → None → Feld verworfen)
    def _lookup(idx: int | None, lst: list[str]) -> str | None:
        if idx is None or not (0 <= idx < len(lst)):
            return None
        return lst[idx]

    brutto_str = _lookup(antwort.brutto_idx, betraege)
    netto_str  = _lookup(antwort.netto_idx,  betraege)
    ust_str    = _lookup(antwort.ust_idx,    betraege)
    datum_str  = _lookup(antwort.datum_idx,  datumsangaben)
    nummer_str = _lookup(antwort.nummer_idx, nummern)

    # 4. Betrag bestätigen – USt optional
    brutto_bestaetigt: Decimal | None = None
    betrag_pruefen_detail = ""

    if brutto_str is not None:
        if netto_str is not None and ust_str is not None:
            # Arithmetik-Prüfung wenn alle drei vorhanden
            brutto_bestaetigt = _pruefe_brutto(netto_str, ust_str, brutto_str, toleranz)
            if brutto_bestaetigt is None:
                n = _parse_betrag_de(netto_str)
                u = _parse_betrag_de(ust_str)
                b = _parse_betrag_de(brutto_str)
                diff = abs(n + u - b) if (n and u and b) else Decimal(0)  # type: ignore[operator]
                betrag_pruefen_detail = (
                    f"Betrag nicht eindeutig (Arithmetik: "
                    f"{netto_str} + {ust_str} ≠ {brutto_str}, Diff. {diff})"
                )
        else:
            # Keine USt → Brutto direkt akzeptiert (Auslandsbeleg, §4 UStG, etc.)
            brutto_bestaetigt = _parse_betrag_de(brutto_str)

    # 5. Finding zusammensetzen – je Feld unabhängig
    info_teile: list[str] = []
    if brutto_bestaetigt is not None:
        info_teile.append(f"Brutto: {brutto_str}")
    if datum_str:
        info_teile.append(f"Datum: {datum_str}")
    if nummer_str:
        info_teile.append(f"Nr.: {nummer_str}")

    if not info_teile and not betrag_pruefen_detail:
        return [Finding(
            rule=SKILL_ID, severity="pruefen",
            title=f"Keine Felder extrahiert: {beleg_rel}",
            detail="LLM hat keine Kandidaten ausgewählt.",
            refs=[Ref(art="beleg", id=beleg_rel)],
        )]

    detail = ", ".join(info_teile)
    if betrag_pruefen_detail:
        detail = (detail + "; " if detail else "") + betrag_pruefen_detail

    severity = "info" if info_teile else "pruefen"
    title = (
        f"Felder extrahiert: {beleg_rel}"
        if severity == "info"
        else f"Betrag nicht eindeutig: {beleg_rel}"
    )
    return [Finding(
        rule=SKILL_ID, severity=severity,
        title=title, detail=detail,
        refs=[Ref(art="beleg", id=beleg_rel)],
    )]


def run(ctx: Context, llm: LlmClient) -> list[Finding]:
    """Extrahiert Felder aus Belegen ohne erkannte Beträge."""
    raw = ctx.config.get("toleranz_betrag", "0.02")
    try:
        toleranz = Decimal(str(raw))
    except Exception:  # noqa: BLE001
        toleranz = _DEFAULT_TOLERANZ

    kopf_laenge = int(ctx.config.get("beleg_kopf_laenge", _DEFAULT_KOPF_LAENGE))
    summen_laenge = int(ctx.config.get("beleg_summen_laenge", _DEFAULT_SUMMEN_LAENGE))

    unlesbar = [b for b in ctx.belege if not b.alle and b.kind != "storno"]
    findings: list[Finding] = []
    for beleg in unlesbar:
        if not beleg.text.strip():
            continue
        findings.extend(
            _extrahiere(beleg.rel, beleg.text, llm, toleranz, kopf_laenge, summen_laenge)
        )
    return findings
