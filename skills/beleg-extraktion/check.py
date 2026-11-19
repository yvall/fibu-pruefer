"""Skill beleg-extraktion: LLM-gestützte Extraktion von Datum/Nummer
aus Belegen, die der deterministische Parser nicht lesen konnte.

Design (v2 – deterministischer Betrag):
- Python wählt den Gesamtbetrag deterministisch aus den Betragskandidaten:
    A) Kandidat = Summe zweier anderer (Netto + USt mit Satz aus config)
    B) Kandidat nächst einem Summen-Stichwort (Gesamt, Total, …)
    C) Größter Kandidat
  Die angewendete Regel steht im Finding-Detail.
  Bei Gleichstand innerhalb einer Regel: "Betrag nicht eindeutig", kein Wert.
- Das LLM liefert nur noch Datum und Nummer (Index-basiert wie bisher).
- Guard entfällt auf Feldebene: ein ungültiger Index wird verworfen,
  die anderen Felder bleiben erhalten.
- USt optional: Weist der Beleg keine USt aus, greift Regel B oder C.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import ROUND_HALF_UP, Decimal
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

# USt-Sätze für Regel A (0 wird für die Arithmetik übersprungen)
_UST_SAETZE_DEFAULT = [Decimal("0.19"), Decimal("0.07"), Decimal("0.00")]

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "extraktion.md").read_text(
    encoding="utf-8"
)

# ---------------------------------------------------------------------------
# JSON-Schema für LLM-Antwort (nur noch Datum + Nummer)
# ---------------------------------------------------------------------------

_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "datum_idx":  {"type": ["integer", "null"]},
        "nummer_idx": {"type": ["integer", "null"]},
    },
    "required": ["datum_idx", "nummer_idx"],
    "additionalProperties": False,
}


class _LlmAntwort(BaseModel):
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

# Stichwörter für deterministischen Betrag-Abgleich (Regel B)
_BRUTTO_KW_RE = re.compile(
    r"\b(?:gesamtbetrag|gesamt|total|zahlbetrag|rechnungsbetrag|"
    r"amount\s+due|summe|endbetrag)\b",
    re.IGNORECASE,
)

# Nummern nach Schlüsselwörtern
_NR_KW_RE = re.compile(
    r"(?:"
    r"Rechnungs(?:nummer|nr\.?)"
    r"|Invoice\s*(?:number|no\.?|nr\.?|#)"
    r"|Receipt\s*(?:no\.?|nr\.?|#)"
    r"|Beleg(?:nummer|-?Nr\.?)"
    r"|Gutschrift(?:-Nr\.?|s(?:-?Nr\.?|nummer))"
    r"|Buchungsnummer"
    r"|Facture"
    r"|Nr\."
    r"|No\."
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

    for m in _AMT_DE_RE.finditer(text):
        val = m.group(1)
        if val not in seen:
            seen.add(val)
            result.append(val)

    for m in _AMT_EN_RE.finditer(text):
        en = m.group(1)
        de = en.replace(",", "").replace(".", ",")
        if de not in seen:
            seen.add(de)
            result.append(de)

    return result[:20]


def _extrahiere_datumsangaben(text: str) -> list[str]:
    """Extrahiert Datumsangaben und normalisiert sie zu DD.MM.YYYY."""
    seen: set[str] = set()
    found: list[tuple[int, str]] = []

    def _add(pos: int, d: int, mo: int, y: str) -> None:
        if 1 <= mo <= 12 and 1 <= d <= 31:
            norm = f"{d:02d}.{mo:02d}.{y}"
            if norm not in seen:
                seen.add(norm)
                found.append((pos, norm))

    for m in re.finditer(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", text):
        _add(m.start(), int(m.group(1)), int(m.group(2)), m.group(3))

    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text):
        _add(m.start(), int(m.group(2)), int(m.group(1)), m.group(3))

    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
        _add(m.start(), int(m.group(3)), int(m.group(2)), m.group(1))

    pat_en = re.compile(
        r"\b(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
        re.IGNORECASE,
    )
    for m in pat_en.finditer(text):
        mo = _MONATE_EN.get(m.group(1).lower(), 0)
        _add(m.start(), int(m.group(2)), mo, m.group(3))

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
        .replace("{{ datumsangaben }}", _fmt(datumsangaben))
        .replace("{{ nummern }}", _fmt(nummern))
    )


# ---------------------------------------------------------------------------
# Deterministischer Betrag (Regeln A → B → C)
# ---------------------------------------------------------------------------

def _waehle_brutto(
    betraege: list[str],
    text: str,
    ust_saetze: list[Decimal] | None = None,
    toleranz: Decimal = _DEFAULT_TOLERANZ,
) -> tuple[str | None, str]:
    """Wählt den Gesamtbetrag deterministisch aus den Kandidaten.

    Returns (brutto_string_in_de_format | None, regel_beschreibung).
    Bei Gleichstand innerhalb einer Regel: (None, "Betrag nicht eindeutig …").
    """
    if not betraege:
        return None, "keine Beträge"

    if ust_saetze is None:
        ust_saetze = _UST_SAETZE_DEFAULT

    werte: list[Decimal | None] = [_parse_betrag_de(b) for b in betraege]

    # Regel A: B = N + U, U/N ≈ Steuersatz
    sieger_a: list[tuple[int, str]] = []  # (brutto_idx, detail)

    for bi, B in enumerate(werte):
        if B is None or B <= 0:
            continue
        matched = False
        for ni, N in enumerate(werte):
            if matched:
                break
            if ni == bi or N is None or N <= 0:
                continue
            U = B - N
            if U < 0:
                continue
            for rate in ust_saetze:
                if rate == 0:
                    continue
                expected_U = (N * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if abs(U - expected_U) > toleranz:
                    continue
                # USt-Kandidat muss auch in der Liste stehen
                for ui, wu in enumerate(werte):
                    if ui == bi or ui == ni or wu is None:
                        continue
                    if abs(wu - U) <= toleranz:
                        rate_pct = int(rate * 100)
                        detail = (
                            f"A: Arithmetik ({betraege[ni]}+{betraege[ui]}"
                            f"={betraege[bi]} USt {rate_pct}%)"
                        )
                        sieger_a.append((bi, detail))
                        matched = True
                        break
                if matched:
                    break

    # Duplikate nach Index entfernen
    seen_idx: set[int] = set()
    unique_a: list[tuple[int, str]] = []
    for idx, detail in sieger_a:
        if idx not in seen_idx:
            seen_idx.add(idx)
            unique_a.append((idx, detail))

    if len(unique_a) == 1:
        idx, detail = unique_a[0]
        return betraege[idx], detail
    if len(unique_a) > 1:
        return None, "Betrag nicht eindeutig (mehrere Arithmetik-Treffer)"

    # Regel B: Nähe zu Stichwörtern (zeilenbasiert)
    lines = text.splitlines()
    kw_zeilen: set[int] = set()
    for li, line in enumerate(lines):
        if _BRUTTO_KW_RE.search(line):
            kw_zeilen.add(li)

    if kw_zeilen:
        # Zeilen je Kandidat bestimmen (DE-Format und ohne Tausender-Trenner)
        # Negative lookbehind/lookahead damit "50,00" nicht in "250,00" matcht.
        cand_zeilen: list[set[int]] = []
        for b_str in betraege:
            b_no_sep = b_str.replace(".", "")
            pat = re.compile(r"(?<!\d)" + re.escape(b_str) + r"(?!\d)")
            pat_ns = re.compile(r"(?<!\d)" + re.escape(b_no_sep) + r"(?!\d)")
            cz: set[int] = set()
            for li, line in enumerate(lines):
                if pat.search(line) or (b_no_sep != b_str and pat_ns.search(line)):
                    cz.add(li)
            cand_zeilen.append(cz)

        # Scoring: gleiche Zeile=0, Folgezeile=1, Vorgängerzeile=2, sonst inf
        scores: list[float] = []
        for cz in cand_zeilen:
            best = float("inf")
            for kl in kw_zeilen:
                for al in cz:
                    if al == kl:
                        best = min(best, 0.0)
                    elif al == kl + 1:
                        best = min(best, 1.0)
                    elif al == kl - 1:
                        best = min(best, 2.0)
            scores.append(best)

        min_score = min(scores)
        if min_score < float("inf"):
            winners_b = [i for i, s in enumerate(scores) if s == min_score]
            if len(winners_b) == 1:
                return betraege[winners_b[0]], "B: Stichwort-Nähe"
            return None, "Betrag nicht eindeutig (Stichwort-Nähe, Gleichstand)"

    # Regel C: größter Betrag
    valid: list[tuple[int, Decimal]] = [
        (i, w) for i, w in enumerate(werte) if w is not None
    ]
    if not valid:
        return None, "keine gültigen Beträge"

    max_val = max(w for _, w in valid)
    winners_c = [i for i, w in valid if w == max_val]
    if len(winners_c) == 1:
        return betraege[winners_c[0]], "C: größter Betrag"
    return None, "Betrag nicht eindeutig (Gleichstand größter Betrag)"


# ---------------------------------------------------------------------------
# Arithmetik-Hilfsfunktionen
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
    ust_saetze: list[Decimal] | None = None,
) -> list[Finding]:
    """Betrag deterministisch; LLM liefert nur Datum und Nummer (Index-basiert)."""
    betraege = _extrahiere_betraege(text)
    datumsangaben = _extrahiere_datumsangaben(text)
    nummern = _extrahiere_nummern(text)

    # 1. Betrag deterministisch wählen
    brutto_str, betrag_regel = _waehle_brutto(betraege, text, ust_saetze, toleranz)

    # 2. LLM nur für Datum + Nummer
    kopf, summenblock = _relevanter_text(text, kopf_laenge, summen_laenge)
    prompt = _baue_prompt(kopf, summenblock, datumsangaben, nummern)
    modell = llm.modell_fuer(SKILL_ID)
    roh = llm.generiere(prompt, json_schema=_JSON_SCHEMA, modell=modell)

    if roh is None:
        log.debug("Kein LLM-Response für %s", beleg_rel)
        if brutto_str is not None:
            return [Finding(
                rule=SKILL_ID, severity="pruefen",
                title=f"LLM-Extraktion teilweise: {beleg_rel}",
                detail=(
                    f"Brutto: {brutto_str}, Betrag-Regel: {betrag_regel}; "
                    "kein LLM-Response für Datum/Nr."
                ),
                refs=[Ref(art="beleg", id=beleg_rel)],
            )]
        return [Finding(
            rule=SKILL_ID, severity="pruefen",
            title=f"LLM-Extraktion fehlgeschlagen: {beleg_rel}",
            detail="Kein LLM-Response.",
            refs=[Ref(art="beleg", id=beleg_rel)],
        )]

    antwort = _parse_llm_antwort(roh)
    if antwort is None:
        log.debug("Parse-Fehler für %s | Roh: %r", beleg_rel, roh[:200])
        if brutto_str is not None:
            return [Finding(
                rule=SKILL_ID, severity="pruefen",
                title=f"LLM-Extraktion teilweise: {beleg_rel}",
                detail=(
                    f"Brutto: {brutto_str}, Betrag-Regel: {betrag_regel}; "
                    f"Antwort nicht auswertbar: {roh[:80]!r}"
                ),
                refs=[Ref(art="beleg", id=beleg_rel)],
            )]
        return [Finding(
            rule=SKILL_ID, severity="pruefen",
            title=f"LLM-Extraktion fehlgeschlagen: {beleg_rel}",
            detail=f"Antwort nicht auswertbar: {roh[:100]!r}",
            refs=[Ref(art="beleg", id=beleg_rel)],
        )]

    # 3. LLM-Indizes → Werte
    def _lookup(idx: int | None, lst: list[str]) -> str | None:
        if idx is None or not (0 <= idx < len(lst)):
            return None
        return lst[idx]

    datum_str = _lookup(antwort.datum_idx, datumsangaben)
    nummer_str = _lookup(antwort.nummer_idx, nummern)

    # 4. Finding zusammensetzen
    info_teile: list[str] = []
    betrag_detail = ""

    if brutto_str is not None:
        info_teile.append(f"Brutto: {brutto_str}")
        info_teile.append(f"Betrag-Regel: {betrag_regel}")
    elif "nicht eindeutig" in betrag_regel:
        betrag_detail = betrag_regel

    if datum_str:
        info_teile.append(f"Datum: {datum_str}")
    if nummer_str:
        info_teile.append(f"Nr.: {nummer_str}")

    if not info_teile and not betrag_detail:
        return [Finding(
            rule=SKILL_ID, severity="pruefen",
            title=f"Keine Felder extrahiert: {beleg_rel}",
            detail="LLM hat keine Kandidaten ausgewählt.",
            refs=[Ref(art="beleg", id=beleg_rel)],
        )]

    detail = ", ".join(info_teile)
    if betrag_detail:
        detail = (detail + "; " if detail else "") + betrag_detail

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

    ust_saetze_pct = ctx.config.get("ust_saetze_prozent", [19, 7, 0])
    try:
        ust_saetze = [Decimal(str(s)) / 100 for s in ust_saetze_pct]
    except Exception:  # noqa: BLE001
        ust_saetze = _UST_SAETZE_DEFAULT

    unlesbar = [b for b in ctx.belege if not b.alle and b.kind != "storno"]
    findings: list[Finding] = []
    for beleg in unlesbar:
        if not beleg.text.strip():
            continue
        findings.extend(
            _extrahiere(
                beleg.rel, beleg.text, llm,
                toleranz, kopf_laenge, summen_laenge, ust_saetze,
            )
        )
    return findings
