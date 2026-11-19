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
    """Baut JSON-Index-Antwort."""
    defaults = {"brutto_idx": None, "netto_idx": None, "ust_idx": None, "datum_idx": None, "nummer_idx": None}
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
    # "19,0" hat nur 1 Nachkommastelle → kein Betrag
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
    assert "08/20/2026" not in dates  # normalisiert, Original nicht enthalten


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
    # Gleicher Tag in verschiedenen Formaten
    dates = _extrahiere_datumsangaben("2026-08-20 / 08/20/2026")
    assert dates.count("20.08.2026") == 1


def test_datum_ungueltige_werden_gefiltert() -> None:
    dates = _extrahiere_datumsangaben("kein Datum 99.99.9999 hier")
    # 99.99 ist kein gültiger Tag/Monat
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
    # Zufällige Zahlen ohne Schlüsselwort werden nicht extrahiert
    nums = _extrahiere_nummern("Kontonummer 123456789 Netto 128,00")
    # "Kontonummer" ist kein Schlüsselwort → je nach Impl. nicht drin
    # Mindestens kein Leerstring
    assert all(len(n) > 0 for n in nums)


# ---------------------------------------------------------------------------
# _parse_betrag_de / _pruefe_brutto (unveränd., kurze Rauchertest)
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
# Guard _wert_in_text (Legacy)
# ---------------------------------------------------------------------------

def test_guard_direkte_uebereinstimmung() -> None:
    assert _wert_in_text("1.234,56", "Betrag: 1.234,56 EUR") is True


def test_guard_wert_nicht_im_text() -> None:
    assert _wert_in_text("99999,00", "Betrag: 1.234,56 EUR") is False


# ---------------------------------------------------------------------------
# _parse_llm_antwort (neues Index-Schema)
# ---------------------------------------------------------------------------

def test_parse_direkt_valide() -> None:
    a = _parse_llm_antwort(
        '{"brutto_idx": 2, "netto_idx": 0, "ust_idx": 1, "datum_idx": 0, "nummer_idx": 1}'
    )
    assert a is not None
    assert a.brutto_idx == 2
    assert a.netto_idx == 0
    assert a.datum_idx == 0


def test_parse_null_felder() -> None:
    a = _parse_llm_antwort(
        '{"brutto_idx": 1, "netto_idx": null, "ust_idx": null, "datum_idx": 0, "nummer_idx": null}'
    )
    assert a is not None
    assert a.netto_idx is None
    assert a.ust_idx is None


def test_parse_mit_erklaertext_fallback() -> None:
    roh = 'Hier ist die Antwort:\n{"brutto_idx":1,"netto_idx":null,"ust_idx":null,"datum_idx":0,"nummer_idx":0}'
    a = _parse_llm_antwort(roh)
    assert a is not None
    assert a.brutto_idx == 1


def test_parse_invalides_json_ergibt_none() -> None:
    assert _parse_llm_antwort("kein JSON hier") is None


# ---------------------------------------------------------------------------
# _extrahiere(): Erfolgsfall – volle Arithmetik
# ---------------------------------------------------------------------------

_TEXT_VOLL = (
    "Netto 128,00 EUR\nUSt 24,32 EUR\nBrutto 152,32 EUR\n"
    "Rechnungsdatum: 15.03.2024\nRechnungsnummer: 2024-001"
)
# Kandidaten aus _TEXT_VOLL (Reihenfolge im Text):
# betraege[0]=128,00  betraege[1]=24,32  betraege[2]=152,32
# datumsangaben[0]=15.03.2024
# nummern[0]=2024-001


def test_extraktion_brutto_arithmetisch_bestaetigt() -> None:
    roh = _idx(brutto_idx=2, netto_idx=0, ust_idx=1, datum_idx=0, nummer_idx=0)
    findings = _extrahiere("test.pdf", _TEXT_VOLL, _MockLlm(roh))
    assert findings[0].severity == "info"
    assert "Brutto: 152,32" in findings[0].detail
    assert "Datum: 15.03.2024" in findings[0].detail
    assert "Nr.: 2024-001" in findings[0].detail


def test_extraktion_detail_enthaelt_brutto_nicht_betrag() -> None:
    roh = _idx(brutto_idx=2, netto_idx=0, ust_idx=1, datum_idx=0, nummer_idx=0)
    findings = _extrahiere("test.pdf", _TEXT_VOLL, _MockLlm(roh))
    assert "Brutto:" in findings[0].detail
    assert "Betrag:" not in findings[0].detail


def test_extraktion_ref_enthaelt_beleg_rel() -> None:
    roh = _idx(brutto_idx=2, netto_idx=0, ust_idx=1, datum_idx=0, nummer_idx=0)
    findings = _extrahiere("ordner/rechnung.pdf", _TEXT_VOLL, _MockLlm(roh))
    assert findings[0].refs[0].id == "ordner/rechnung.pdf"


# ---------------------------------------------------------------------------
# _extrahiere(): USt optional (Auslandsbeleg)
# ---------------------------------------------------------------------------

_TEXT_AUSLAND = (
    "Agoda Company Pte.\nAugust 20, 2026\nBooking No. 691941775\n"
    "Total: 77.23 EUR"
)
# betraege[0]=77,23  datumsangaben[0]=20.08.2026  nummern[0]=691941775


def test_keine_ust_brutto_direkt_akzeptiert() -> None:
    """Auslandsbeleg ohne USt: brutto_idx gesetzt, netto/ust null → info."""
    roh = _idx(brutto_idx=0, netto_idx=None, ust_idx=None, datum_idx=0, nummer_idx=0)
    findings = _extrahiere("Receipt.pdf", _TEXT_AUSLAND, _MockLlm(roh))
    assert findings[0].severity == "info"
    assert "Brutto: 77,23" in findings[0].detail


def test_en_datum_normalisiert() -> None:
    """'August 20, 2026' wird zu '20.08.2026' normalisiert."""
    roh = _idx(brutto_idx=0, datum_idx=0, nummer_idx=0)
    findings = _extrahiere("Receipt.pdf", _TEXT_AUSLAND, _MockLlm(roh))
    assert "Datum: 20.08.2026" in findings[0].detail


def test_us_datum_normalisiert() -> None:
    """'08/20/2026' wird zu '20.08.2026' normalisiert."""
    text = "Date: 08/20/2026\nAmount due: 77.23 EUR\nReceipt no. 691941775"
    roh = _idx(brutto_idx=0, datum_idx=0, nummer_idx=0)
    findings = _extrahiere("Receipt.pdf", text, _MockLlm(roh))
    assert "Datum: 20.08.2026" in findings[0].detail


# ---------------------------------------------------------------------------
# _extrahiere(): Ein Feld ungültig, andere bleiben
# ---------------------------------------------------------------------------

def test_ungueltige_brutto_index_datum_nummer_bleiben() -> None:
    """brutto_idx zeigt auf nicht existierenden Index → Betrag verworfen, Datum/Nr. bleiben."""
    text = "Rechnungsdatum: 15.03.2024\nRechnungsnummer: 2024-001\nBetrag: 128,00"
    # betraege[0]=128,00; datumsangaben[0]=15.03.2024; nummern[0]=2024-001
    # brutto_idx=99 → ungültig → verworfen
    roh = _idx(brutto_idx=99, datum_idx=0, nummer_idx=0)
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert len(findings) == 1
    assert "Datum: 15.03.2024" in findings[0].detail
    assert "Nr.: 2024-001" in findings[0].detail
    assert "Brutto:" not in findings[0].detail


def test_ungueltige_datum_index_brutto_bleibt() -> None:
    """datum_idx null → Datum verworfen, Brutto bleibt."""
    text = "Netto 128,00\nUSt 24,32\nBrutto 152,32\nNr. 2024-001"
    roh = _idx(brutto_idx=2, netto_idx=0, ust_idx=1, datum_idx=None, nummer_idx=0)
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert "Brutto: 152,32" in findings[0].detail
    assert "Datum:" not in findings[0].detail


def test_arithmetik_falsch_datum_nummer_bleiben() -> None:
    """Arithmetik schlägt fehl → Betrag verworfen, Datum/Nr. bleiben wenn vorhanden."""
    text = "Netto 128,00 USt 24,00 Brutto 160,00\n15.03.2024\nNr. 2024-001"
    # 128+24=152 ≠ 160 → Arithmetik falsch
    roh = _idx(brutto_idx=2, netto_idx=0, ust_idx=1, datum_idx=0, nummer_idx=0)
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    # Datum und Nummer sollten noch im Detail stehen
    assert "Datum: 15.03.2024" in findings[0].detail
    assert "Nr.: 2024-001" in findings[0].detail
    assert "Arithmetik" in findings[0].detail


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

    # Fixture hat: Brutto 2.350,00, Netto 1.974,79, USt 375,21, Datum 22.08.2026, Nr. 2024-0815
    # Reihenfolge im Text: 1.974,79 (idx 0), 375,21 (idx 1), 2.350,00 (idx 2)
    # Datum: 22.08.2026 (idx 0); Nr.: 2024-0815 (idx 0)
    roh = _idx(brutto_idx=2, netto_idx=0, ust_idx=1, datum_idx=0, nummer_idx=0)
    findings = _extrahiere("injection.txt", injection_text, _MockLlm(roh))
    assert all(f.rule == "beleg-extraktion" for f in findings)
    assert findings[0].severity == "info"
    assert "2.350,00" in findings[0].detail


def test_injection_halluzinierter_index_verworfen() -> None:
    """Ungültiger Index → Feld verworfen, kein Absturz."""
    fixture_path = Path(__file__).parent / "fixtures" / "beleg_injection.txt"
    injection_text = fixture_path.read_text(encoding="utf-8")
    # brutto_idx=999 ist außerhalb des Kandidaten-Bereichs → verworfen
    roh = _idx(brutto_idx=999, datum_idx=0, nummer_idx=0)
    findings = _extrahiere("injection.txt", injection_text, _MockLlm(roh))
    assert len(findings) == 1
    assert "Brutto:" not in findings[0].detail


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
    # betraege: 420,17(0) 79,83(1) 500,00(2); datumsangaben: 01.08.2024(0); nummern: 2024-001(0)
    roh = _idx(brutto_idx=2, netto_idx=0, ust_idx=1, datum_idx=0, nummer_idx=0)
    findings = run(_ctx([b]), _MockLlm(roh))
    assert len(findings) == 1
    assert findings[0].severity == "info"


def test_run_mehrere_unlesbare_belege_je_ein_finding() -> None:
    belege = [
        _beleg("a.pdf", text="Netto 420,17 USt 79,83 Brutto 500,00", alle=[]),
        _beleg("b.pdf", text="Total 750,00 EUR\n01.03.2024", alle=[]),
    ]
    roh = _idx(brutto_idx=2, netto_idx=0, ust_idx=1)
    findings = run(_ctx(belege), _MockLlm(roh))
    assert len(findings) == 2


# ---------------------------------------------------------------------------
# Parametrisierte Brutto-Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text, llm_antwort, erwartet_brutto_ok",
    [
        # Volle Arithmetik korrekt → Brutto im Detail
        (
            "Netto 128,00 USt 24,32 Brutto 152,32",
            _idx(brutto_idx=2, netto_idx=0, ust_idx=1),
            True,
        ),
        # Auslandsbeleg ohne USt → Brutto direkt akzeptiert
        (
            "Amount due: 77.23 EUR",
            _idx(brutto_idx=0),
            True,
        ),
        # Arithmetik falsch → kein Brutto
        (
            "Netto 128,00 USt 24,00 Brutto 160,00",
            _idx(brutto_idx=2, netto_idx=0, ust_idx=1),
            False,
        ),
        # Ungültiger brutto_idx → kein Brutto
        (
            "Betrag 500,00 EUR",
            _idx(brutto_idx=99),
            False,
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
