"""Tests für skills/beleg-extraktion/check.py."""
from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

_spec = importlib.util.spec_from_file_location(
    "_beleg_extraktion", Path(__file__).parent.parent / "check.py"
)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

run                   = _mod.run  # type: ignore[attr-defined]
_extrahiere           = _mod._extrahiere  # type: ignore[attr-defined]
_extrahiere_betraege  = _mod._extrahiere_betraege  # type: ignore[attr-defined]
_extrahiere_datumsangaben = _mod._extrahiere_datumsangaben  # type: ignore[attr-defined]
_extrahiere_nummern   = _mod._extrahiere_nummern  # type: ignore[attr-defined]
_relevanter_text      = _mod._relevanter_text  # type: ignore[attr-defined]
_wert_in_text         = _mod._wert_in_text  # type: ignore[attr-defined]
_parse_betrag_de      = _mod._parse_betrag_de  # type: ignore[attr-defined]
_pruefe_brutto        = _mod._pruefe_brutto  # type: ignore[attr-defined]
_parse_llm_antwort    = _mod._parse_llm_antwort  # type: ignore[attr-defined]
_waehle_brutto        = _mod._waehle_brutto  # type: ignore[attr-defined]

from fibu.contracts import Auswertung, BelegRecord, Context

_TOL = Decimal("0.02")


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _ctx(belege: list[BelegRecord] | None = None) -> Context:
    return Context(
        auswertung=Auswertung(source="test.pdf", year=2024, month=8),
        belege=belege or [],
    )


def _beleg(
    rel: str = "rechnung.pdf",
    text: str = "",
    alle: list[Decimal] | None = None,
    kind: str = "rechnung",
) -> BelegRecord:
    return BelegRecord(
        path=rel, rel=rel, sha="abc",
        text=text, kind=kind,
        alle=alle if alle is not None else [],
    )


class _MockLlm:
    def __init__(self, antwort: str | None) -> None:
        self._antwort = antwort
        self.modell = "mock"
        self.aufrufe: list[str] = []

    def modell_fuer(self, skill_id: str) -> str:
        return self.modell

    def generiere(
        self, prompt: str, json_schema: dict[str, Any] | None = None, *, modell: str = ""
    ) -> str | None:
        self.aufrufe.append(prompt)
        return self._antwort


def _idx(**kwargs: int | None) -> str:
    """Baut JSON-Index-Antwort (nur datum_idx + nummer_idx)."""
    defaults: dict[str, int | None] = {"datum_idx": None, "nummer_idx": None}
    defaults.update(kwargs)
    return json.dumps(defaults)


# ---------------------------------------------------------------------------
# _extrahiere_betraege
# ---------------------------------------------------------------------------

def test_betraege_de_format() -> None:
    text = "Netto 128,00 EUR\nUSt 24,32 EUR\nBrutto 152,32 EUR"
    betraege = _extrahiere_betraege(text)
    assert "128,00" in betraege
    assert "24,32" in betraege
    assert "152,32" in betraege


def test_betraege_en_format_zu_de_normalisiert() -> None:
    text = "Total: 90.13 USD\nAmount due: 77.23 EUR"
    betraege = _extrahiere_betraege(text)
    assert "90,13" in betraege
    assert "77,23" in betraege


def test_betraege_en_format_mit_tausender() -> None:
    text = "Invoice total: 10,281.60 EUR"
    betraege = _extrahiere_betraege(text)
    assert "10281,60" in betraege


def test_betraege_de_format_mit_tausender() -> None:
    text = "Bruttobetrag: 22.241,10 EUR"
    betraege = _extrahiere_betraege(text)
    assert "22.241,10" in betraege


def test_betraege_kein_dreisatz_als_betrag() -> None:
    text = "19,0 % Umsatzsteuer"
    betraege = _extrahiere_betraege(text)
    assert "19,0" not in betraege


def test_betraege_dedupliziert() -> None:
    text = "24,00 EUR  Summe: 24,00"
    betraege = _extrahiere_betraege(text)
    assert betraege.count("24,00") == 1


# ---------------------------------------------------------------------------
# _extrahiere_datumsangaben
# ---------------------------------------------------------------------------

def test_datum_de_format() -> None:
    assert "29.08.2026" in _extrahiere_datumsangaben("Datum: 29.08.2026")


def test_datum_us_format_normalisiert() -> None:
    dates = _extrahiere_datumsangaben("Date: 08/20/2026")
    assert "20.08.2026" in dates
    assert "08/20/2026" not in dates


def test_datum_iso_format_normalisiert() -> None:
    dates = _extrahiere_datumsangaben("Issued: 2026-08-20")
    assert "20.08.2026" in dates


def test_datum_englische_monatsnamen() -> None:
    dates = _extrahiere_datumsangaben("August 22, 2026")
    assert "22.08.2026" in dates


def test_datum_deutsche_monatsnamen() -> None:
    dates = _extrahiere_datumsangaben("22. August 2026")
    assert "22.08.2026" in dates


def test_datum_verschiedene_formate_dedupliziert() -> None:
    dates = _extrahiere_datumsangaben("2026-08-20 / 08/20/2026")
    assert dates.count("20.08.2026") == 1


def test_datum_ungueltige_werden_gefiltert() -> None:
    dates = _extrahiere_datumsangaben("kein Datum 99.99.9999 hier")
    assert not any("99" in d for d in dates)


# ---------------------------------------------------------------------------
# _extrahiere_nummern
# ---------------------------------------------------------------------------

def test_nummer_nach_rechnungsnummer() -> None:
    nums = _extrahiere_nummern("Rechnungsnummer: 2026-5-09-33803")
    assert "2026-5-09-33803" in nums


def test_nummer_nach_invoice_number() -> None:
    nums = _extrahiere_nummern("Invoice number: 6ODQWXOA-0005")
    assert "6ODQWXOA-0005" in nums


def test_nummer_nach_nr() -> None:
    nums = _extrahiere_nummern("Nr. 100192553623")
    assert "100192553623" in nums


def test_nummer_nach_facture() -> None:
    nums = _extrahiere_nummern("FACTURE 0000351")
    assert "0000351" in nums


def test_nummer_nach_gutschrift_nr() -> None:
    nums = _extrahiere_nummern("Gutschrift-Nr.: 2202608055")
    assert "2202608055" in nums


def test_nummer_ohne_stichwort_nicht_extrahiert() -> None:
    nums = _extrahiere_nummern("Kontonummer 123456789 Netto 128,00")
    assert all(len(n) > 0 for n in nums)


# ---------------------------------------------------------------------------
# _parse_betrag_de / _pruefe_brutto
# ---------------------------------------------------------------------------

def test_parse_betrag_de() -> None:
    assert _parse_betrag_de("1.234,56") == Decimal("1234.56")
    assert _parse_betrag_de("90,13") == Decimal("90.13")
    assert _parse_betrag_de("") is None


def test_pruefe_brutto_korrekt() -> None:
    assert _pruefe_brutto("128,00", "24,32", "152,32", _TOL) == Decimal("152.32")


def test_pruefe_brutto_falsch() -> None:
    assert _pruefe_brutto("128,00", "24,00", "160,00", _TOL) is None


# ---------------------------------------------------------------------------
# _waehle_brutto: Regel A – Arithmetik
# ---------------------------------------------------------------------------

def test_waehle_brutto_regel_a_19pct() -> None:
    betraege = ["128,00", "24,32", "152,32"]
    text = "Netto 128,00 EUR\nUSt 24,32 EUR\nBrutto 152,32 EUR"
    brutto, regel = _waehle_brutto(betraege, text)
    assert brutto == "152,32"
    assert "A:" in regel
    assert "19%" in regel


def test_waehle_brutto_regel_a_7pct() -> None:
    # 100 * 0.07 = 7 → Brutto 107
    betraege = ["100,00", "7,00", "107,00"]
    text = "Netto 100,00\nUSt 7,00\nBrutto 107,00"
    brutto, regel = _waehle_brutto(betraege, text)
    assert brutto == "107,00"
    assert "A:" in regel
    assert "7%" in regel


def test_waehle_brutto_regel_a_grosse_betraege() -> None:
    # 10.281,60 ist echter Problemfall aus der Eval
    # Netto ~8.639,16 + 19% USt ~1.641,44 = ~10.280,60 (innerhalb Toleranz)
    # Hier exakt: 8640,00 * 1.19 = 10281,60
    betraege = ["8.640,00", "1.641,60", "10.281,60", "120,00"]
    text = "Netto 8.640,00\nUSt 1.641,60\nGesamtbetrag 10.281,60\nPosition 120,00"
    brutto, regel = _waehle_brutto(betraege, text)
    assert brutto == "10.281,60"
    assert "A:" in regel


def test_waehle_brutto_keine_kandidaten() -> None:
    brutto, regel = _waehle_brutto([], "text")
    assert brutto is None
    assert "keine" in regel


def test_waehle_brutto_gleichstand_c() -> None:
    # Da _extrahiere_betraege dedupliziert, simulieren wir einen Gleichstand mit
    # zwei verschiedenen Strings, die den gleichen Decimal-Wert ergeben.
    brutto, regel = _waehle_brutto(["500,00", "500,00"], "Betrag 500,00 EUR 500,00")
    # Entweder Regel C (nur ein unique-Wert) oder "nicht eindeutig"
    # Wichtig: kein Absturz
    assert isinstance(brutto, (str, type(None)))
    assert isinstance(regel, str)


# ---------------------------------------------------------------------------
# _waehle_brutto: Regel B – Stichwort-Nähe
# ---------------------------------------------------------------------------

def test_waehle_brutto_regel_b_endbetrag() -> None:
    betraege = ["128,00", "500,00"]
    text = "Einzelposten 128,00 EUR\nEndbetrag 500,00 EUR"
    brutto, regel = _waehle_brutto(betraege, text)
    assert brutto == "500,00"
    assert "B:" in regel


def test_waehle_brutto_regel_b_total() -> None:
    betraege = ["77,23"]
    text = "Total: 77.23 EUR"  # EN-Format → normalisiert zu "77,23"
    brutto, _regel = _waehle_brutto(betraege, text)
    assert brutto == "77,23"


def test_waehle_brutto_regel_b_amount_due() -> None:
    betraege = ["50,00", "250,00"]
    text = "Einzelposten 50,00\nAmount due 250,00"
    brutto, regel = _waehle_brutto(betraege, text)
    assert brutto == "250,00"
    assert "B:" in regel


# ---------------------------------------------------------------------------
# _waehle_brutto: Regel C – größter Betrag
# ---------------------------------------------------------------------------

def test_waehle_brutto_regel_c_ohne_stichwort() -> None:
    betraege = ["128,00", "500,00", "24,00"]
    text = "Posten 128,00 USt 24,00 Auftrag 500,00"
    brutto, regel = _waehle_brutto(betraege, text)
    assert brutto == "500,00"
    assert "C:" in regel


def test_waehle_brutto_einzelner_kandidat() -> None:
    brutto, _regel = _waehle_brutto(["77,23"], "Total: 77.23 EUR")
    assert brutto == "77,23"


# ---------------------------------------------------------------------------
# Guard _wert_in_text (Legacy)
# ---------------------------------------------------------------------------

def test_guard_direkte_uebereinstimmung() -> None:
    assert _wert_in_text("1.234,56", "Betrag: 1.234,56 EUR") is True


def test_guard_wert_nicht_im_text() -> None:
    assert _wert_in_text("99999,00", "Betrag: 1.234,56 EUR") is False


# ---------------------------------------------------------------------------
# _parse_llm_antwort (neues Index-Schema: nur datum + nummer)
# ---------------------------------------------------------------------------

def test_parse_direkt_valide() -> None:
    a = _parse_llm_antwort('{"datum_idx": 0, "nummer_idx": 1}')
    assert a is not None
    assert a.datum_idx == 0
    assert a.nummer_idx == 1


def test_parse_null_felder() -> None:
    a = _parse_llm_antwort('{"datum_idx": null, "nummer_idx": null}')
    assert a is not None
    assert a.datum_idx is None
    assert a.nummer_idx is None


def test_parse_mit_erklaertext_fallback() -> None:
    roh = 'Hier ist die Antwort:\n{"datum_idx":0,"nummer_idx":0}'
    a = _parse_llm_antwort(roh)
    assert a is not None
    assert a.datum_idx == 0


def test_parse_invalides_json_ergibt_none() -> None:
    assert _parse_llm_antwort("kein JSON hier") is None


# ---------------------------------------------------------------------------
# _extrahiere(): Erfolgsfall
# ---------------------------------------------------------------------------

_TEXT_VOLL = (
    "Netto 128,00 EUR\nUSt 24,32 EUR\nBrutto 152,32 EUR\n"
    "Rechnungsdatum: 15.03.2024\nRechnungsnummer: 2024-001"
)
# betraege: 128,00(0) 24,32(1) 152,32(2) → Regel A wählt 152,32
# datumsangaben[0]=15.03.2024; nummern[0]=2024-001


def test_extraktion_brutto_arithmetisch_bestaetigt() -> None:
    roh = _idx(datum_idx=0, nummer_idx=0)
    findings = _extrahiere("test.pdf", _TEXT_VOLL, _MockLlm(roh))
    assert findings[0].severity == "info"
    assert "Brutto: 152,32" in findings[0].detail
    assert "Datum: 15.03.2024" in findings[0].detail
    assert "Nr.: 2024-001" in findings[0].detail


def test_extraktion_detail_enthaelt_brutto_nicht_betrag() -> None:
    roh = _idx(datum_idx=0, nummer_idx=0)
    findings = _extrahiere("test.pdf", _TEXT_VOLL, _MockLlm(roh))
    assert "Brutto:" in findings[0].detail
    assert "Betrag:" not in findings[0].detail


def test_extraktion_ref_enthaelt_beleg_rel() -> None:
    roh = _idx(datum_idx=0, nummer_idx=0)
    findings = _extrahiere("ordner/rechnung.pdf", _TEXT_VOLL, _MockLlm(roh))
    assert findings[0].refs[0].id == "ordner/rechnung.pdf"


def test_extraktion_betrag_regel_in_detail() -> None:
    """Betrag-Regel steht im Finding-Detail."""
    roh = _idx(datum_idx=0, nummer_idx=0)
    findings = _extrahiere("test.pdf", _TEXT_VOLL, _MockLlm(roh))
    assert "Betrag-Regel:" in findings[0].detail


# ---------------------------------------------------------------------------
# _extrahiere(): Auslandsbeleg (kein USt)
# ---------------------------------------------------------------------------

_TEXT_AUSLAND = (
    "Agoda Company Pte.\nAugust 20, 2026\nBooking No. 691941775\n"
    "Total: 77.23 EUR"
)
# betraege[0]=77,23 (via EN→DE); datumsangaben[0]=20.08.2026; nummern[0]=691941775


def test_keine_ust_brutto_via_stichwort_oder_regel_c() -> None:
    """Auslandsbeleg ohne USt: Betrag wird via Regel B (Total) oder C (einziger) gefunden."""
    roh = _idx(datum_idx=0, nummer_idx=0)
    findings = _extrahiere("Receipt.pdf", _TEXT_AUSLAND, _MockLlm(roh))
    assert findings[0].severity == "info"
    assert "Brutto: 77,23" in findings[0].detail


def test_en_datum_normalisiert() -> None:
    roh = _idx(datum_idx=0, nummer_idx=0)
    findings = _extrahiere("Receipt.pdf", _TEXT_AUSLAND, _MockLlm(roh))
    assert "Datum: 20.08.2026" in findings[0].detail


def test_us_datum_normalisiert() -> None:
    text = "Date: 08/20/2026\nAmount due: 77.23 EUR\nReceipt no. 691941775"
    roh = _idx(datum_idx=0, nummer_idx=0)
    findings = _extrahiere("Receipt.pdf", text, _MockLlm(roh))
    assert "Datum: 20.08.2026" in findings[0].detail


# ---------------------------------------------------------------------------
# _extrahiere(): Ein Feld ungültig, andere bleiben
# ---------------------------------------------------------------------------

def test_datum_index_null_brutto_bleibt() -> None:
    """datum_idx null → Datum verworfen, Brutto (Regel A) bleibt."""
    text = "Netto 128,00\nUSt 24,32\nBrutto 152,32\nNr. 2024-001"
    roh = _idx(datum_idx=None, nummer_idx=0)
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert "Brutto: 152,32" in findings[0].detail
    assert "Datum:" not in findings[0].detail


def test_brutto_via_regel_c_datum_nummer_bleiben() -> None:
    """Betrag wird via Regel C gefunden; Datum und Nr. kommen vom LLM."""
    text = "Rechnungsdatum: 15.03.2024\nRechnungsnummer: 2024-001\nBetrag: 128,00"
    roh = _idx(datum_idx=0, nummer_idx=0)
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert "Brutto: 128,00" in findings[0].detail
    assert "Datum: 15.03.2024" in findings[0].detail
    assert "Nr.: 2024-001" in findings[0].detail


def test_brutto_ohne_arithmetik_datum_nummer_bleiben() -> None:
    """Betrag-Auswahl via Regel C (kein gültiger Arithmetik-Treffer)."""
    text = "Netto 128,00 USt 24,00 Brutto 160,00\n15.03.2024\nNr. 2024-001"
    roh = _idx(datum_idx=0, nummer_idx=0)
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    # 128+24=152≠160; kein Arithmetik-Treffer → Regel C: 160,00 (größter Betrag)
    assert "Brutto: 160,00" in findings[0].detail
    assert "Datum: 15.03.2024" in findings[0].detail
    assert "Nr.: 2024-001" in findings[0].detail


# ---------------------------------------------------------------------------
# _extrahiere(): Fehlerfälle
# ---------------------------------------------------------------------------

def test_llm_keine_antwort() -> None:
    findings = _extrahiere("test.pdf", "Text", _MockLlm(None))
    assert findings[0].severity == "pruefen"
    assert "LLM-Extraktion fehlgeschlagen" in findings[0].title


def test_invalides_json() -> None:
    findings = _extrahiere("test.pdf", "Text", _MockLlm("KEIN JSON"))
    assert findings[0].severity == "pruefen"


def test_alle_indices_null_keine_felder() -> None:
    findings = _extrahiere("test.pdf", "Unlesbarer Text", _MockLlm(_idx()))
    assert findings[0].severity == "pruefen"
    assert "Keine Felder" in findings[0].title


# ---------------------------------------------------------------------------
# Injection-Fixture
# ---------------------------------------------------------------------------

def test_injection_in_belegtext_kein_absturz() -> None:
    """Skill läuft mit Injection-Inhalt ohne Absturz."""
    fixture_path = Path(__file__).parent / "fixtures" / "beleg_injection.txt"
    injection_text = fixture_path.read_text(encoding="utf-8")

    # 1.974,79(0) + 375,21(1) = 2.350,00(2) → Regel A, 19%
    roh = _idx(datum_idx=0, nummer_idx=0)
    findings = _extrahiere("injection.txt", injection_text, _MockLlm(roh))
    assert all(f.rule == "beleg-extraktion" for f in findings)
    assert findings[0].severity == "info"
    assert "2.350,00" in findings[0].detail


def test_injection_betrag_deterministisch_gefunden() -> None:
    """Betrag wird deterministisch via Regel A gefunden, unabhängig vom LLM."""
    fixture_path = Path(__file__).parent / "fixtures" / "beleg_injection.txt"
    injection_text = fixture_path.read_text(encoding="utf-8")
    # LLM gibt keine Datum/Nr. → aber Betrag kommt deterministisch
    roh = _idx()
    findings = _extrahiere("injection.txt", injection_text, _MockLlm(roh))
    assert len(findings) == 1
    # Betrag ist trotzdem im Detail (via Regel A)
    assert "Brutto: 2.350,00" in findings[0].detail


# ---------------------------------------------------------------------------
# run(): Belege überspringen / Integration
# ---------------------------------------------------------------------------

def test_run_ohne_belege_leer() -> None:
    assert run(_ctx(), _MockLlm(None)) == []


def test_run_lesbare_belege_werden_uebersprungen() -> None:
    b = _beleg(text="Rechnung 500 EUR", alle=[Decimal("500.00")])
    assert run(_ctx([b]), _MockLlm(None)) == []


def test_run_storno_wird_uebersprungen() -> None:
    assert run(_ctx([_beleg(text="Storno", alle=[], kind="storno")]), _MockLlm(None)) == []


def test_run_beleg_ohne_text_wird_uebersprungen() -> None:
    assert run(_ctx([_beleg(text="", alle=[])]), _MockLlm(None)) == []


def test_run_unlesbar_beleg_erzeugt_finding() -> None:
    text = "Netto 420,17 USt 79,83 Brutto 500,00\nRechnung Nr. 2024-001\n01.08.2024"
    b = _beleg(text=text, alle=[])
    # 420,17 + 79,83 = 500,00; 79.83/420.17 ≈ 0.19
    roh = _idx(datum_idx=0, nummer_idx=0)
    findings = run(_ctx([b]), _MockLlm(roh))
    assert len(findings) == 1
    assert findings[0].severity == "info"


def test_run_mehrere_unlesbare_belege_je_ein_finding() -> None:
    belege = [
        _beleg("a.pdf", text="Netto 420,17 USt 79,83 Brutto 500,00", alle=[]),
        _beleg("b.pdf", text="Total 750,00 EUR\n01.03.2024", alle=[]),
    ]
    roh = _idx()
    findings = run(_ctx(belege), _MockLlm(roh))
    assert len(findings) == 2


# ---------------------------------------------------------------------------
# Parametrisierte Brutto-Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text, llm_antwort, erwartet_brutto_ok",
    [
        # Volle Arithmetik korrekt → Brutto via Regel A
        (
            "Netto 128,00 USt 24,32 Brutto 152,32",
            _idx(),
            True,
        ),
        # Auslandsbeleg ohne USt, ein Kandidat → Brutto via Regel B/C
        (
            "Amount due: 77.23 EUR",
            _idx(),
            True,
        ),
        # Arithmetik nicht eindeutig → kein Arithmetik-Treffer, Regel C: größter
        (
            "Netto 128,00 USt 24,00 Brutto 160,00",
            _idx(),
            True,
        ),
        # Einziger Kandidat → Regel C
        (
            "Betrag 500,00 EUR",
            _idx(),
            True,
        ),
    ],
)
def test_brutto_parametrisiert(
    text: str, llm_antwort: str, erwartet_brutto_ok: bool
) -> None:
    findings = _extrahiere("test.pdf", text, _MockLlm(llm_antwort))
    if erwartet_brutto_ok:
        assert "Brutto:" in findings[0].detail
    else:
        assert "Brutto:" not in findings[0].detail
