"""Tests für skills/beleg-extraktion/check.py."""
from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

_spec = importlib.util.spec_from_file_location(
    "_beleg_extraktion", Path(__file__).parent.parent / "check.py"
)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

run = _mod.run  # type: ignore[attr-defined]
_extrahiere = _mod._extrahiere  # type: ignore[attr-defined]
_wert_in_text = _mod._wert_in_text  # type: ignore[attr-defined]
_parse_llm_antwort = _mod._parse_llm_antwort  # type: ignore[attr-defined]
_pruefe_brutto = _mod._pruefe_brutto  # type: ignore[attr-defined]
_parse_betrag_de = _mod._parse_betrag_de  # type: ignore[attr-defined]

from fibu.contracts import Auswertung, BelegRecord, Context

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

_TOL = Decimal("0.02")


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


def _antwort(
    netto: str = "", ust: str = "", brutto: str = "",
    datum: str = "", nummer: str = "",
) -> str:
    return (
        f'{{"netto":"{netto}","ust":"{ust}","brutto":"{brutto}",'
        f'"datum":"{datum}","nummer":"{nummer}"}}'
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


# ---------------------------------------------------------------------------
# _parse_betrag_de
# ---------------------------------------------------------------------------

def test_parse_betrag_de_format() -> None:
    assert _parse_betrag_de("1.234,56") == Decimal("1234.56")


def test_parse_betrag_en_format() -> None:
    assert _parse_betrag_de("128.00") == Decimal("128.00")


def test_parse_betrag_einfach() -> None:
    assert _parse_betrag_de("152,32") == Decimal("152.32")


def test_parse_betrag_leer_ergibt_none() -> None:
    assert _parse_betrag_de("") is None
    assert _parse_betrag_de("  ") is None


def test_parse_betrag_kein_zahl_ergibt_none() -> None:
    assert _parse_betrag_de("KEIN BETRAG") is None


# ---------------------------------------------------------------------------
# _pruefe_brutto (Arithmetik-Check)
# ---------------------------------------------------------------------------

def test_pruefe_brutto_korrekte_arithmetik() -> None:
    assert _pruefe_brutto("128,00", "24,32", "152,32", _TOL) == Decimal("152.32")


def test_pruefe_brutto_toleranz_grenzfall() -> None:
    # 128.00 + 24.32 = 152.32; brutto = 152.33 → Diff = 0.01 ≤ 0.02 → ok
    assert _pruefe_brutto("128,00", "24,32", "152,33", _TOL) == Decimal("152.33")


def test_pruefe_brutto_arithmetik_falsch() -> None:
    # 128 + 24 = 152 ≠ 160 → None
    assert _pruefe_brutto("128,00", "24,00", "160,00", _TOL) is None


def test_pruefe_brutto_nur_brutto_ohne_netto_ust() -> None:
    # Einzelner Betrag wird nicht als Brutto gewertet
    assert _pruefe_brutto("", "", "152,32", _TOL) is None


def test_pruefe_brutto_nur_netto_ohne_brutto() -> None:
    assert _pruefe_brutto("128,00", "", "", _TOL) is None


def test_pruefe_brutto_en_format() -> None:
    assert _pruefe_brutto("128.00", "24.32", "152.32", _TOL) == Decimal("152.32")


# ---------------------------------------------------------------------------
# Guard _wert_in_text
# ---------------------------------------------------------------------------

def test_guard_leerer_wert_immer_true() -> None:
    assert _wert_in_text("", "beliebiger Text") is True
    assert _wert_in_text("  ", "beliebiger Text") is True


def test_guard_direkte_uebereinstimmung() -> None:
    assert _wert_in_text("1.234,56", "Betrag: 1.234,56 EUR") is True


def test_guard_de_format_in_en_text() -> None:
    assert _wert_in_text("1.234,56", "Total: 1234.56 USD") is True


def test_guard_en_format_in_de_text() -> None:
    assert _wert_in_text("1234.56", "Gesamt: 1.234,56 EUR") is True


def test_guard_datum_direkt() -> None:
    assert _wert_in_text("15.03.2024", "Rechnungsdatum: 15.03.2024") is True


def test_guard_nummer_mit_bindestrich() -> None:
    assert _wert_in_text("2024-001", "Rg.-Nr. 2024-001") is True


def test_guard_wert_nicht_im_text() -> None:
    assert _wert_in_text("99999,00", "Betrag: 1.234,56 EUR") is False


def test_guard_halluzinierter_wert() -> None:
    assert _wert_in_text("PHANTOM-WERT", "Rechnung Nr. 2024-001") is False


# ---------------------------------------------------------------------------
# _parse_llm_antwort (Structured Output + json.loads-Fallback)
# ---------------------------------------------------------------------------

def test_parse_direkt_valide() -> None:
    a = _parse_llm_antwort(
        '{"netto":"128,00","ust":"24,32","brutto":"152,32","datum":"15.03.2024","nummer":"2024-001"}'
    )
    assert a is not None
    assert a.brutto == "152,32"
    assert a.netto == "128,00"
    assert a.datum == "15.03.2024"


def test_parse_mit_erklaertext_fallback() -> None:
    roh = 'Hier:\n{"netto":"84,03","ust":"15,97","brutto":"100,00","datum":"","nummer":"RG-42"}'
    a = _parse_llm_antwort(roh)
    assert a is not None
    assert a.brutto == "100,00"
    assert a.nummer == "RG-42"


def test_parse_leere_felder() -> None:
    a = _parse_llm_antwort('{"netto":"","ust":"","brutto":"","datum":"","nummer":""}')
    assert a is not None
    assert a.brutto == ""


def test_parse_invalides_json_ergibt_none() -> None:
    a = _parse_llm_antwort("Das ist kein JSON und auch kein {Objekt}")
    assert a is None


# ---------------------------------------------------------------------------
# run(): Belege überspringen
# ---------------------------------------------------------------------------

def test_run_ohne_belege_leer() -> None:
    assert run(_ctx(), _MockLlm(None)) == []


def test_run_lesbare_belege_werden_uebersprungen() -> None:
    b = _beleg(text="Rechnung 500 EUR", alle=[Decimal("500.00")])
    assert run(_ctx([b]), _MockLlm(None)) == []


def test_run_storno_wird_uebersprungen() -> None:
    b = _beleg(text="Stornierung", alle=[], kind="storno")
    assert run(_ctx([b]), _MockLlm(None)) == []


def test_run_beleg_ohne_text_wird_uebersprungen() -> None:
    b = _beleg(text="", alle=[])
    assert run(_ctx([b]), _MockLlm(None)) == []


# ---------------------------------------------------------------------------
# _extrahiere(): Erfolgsfall – Arithmetik korrekt
# ---------------------------------------------------------------------------

def _text_mit_allen_feldern() -> str:
    return (
        "Rechnung 2024-001\n15.03.2024\n"
        "Netto: 1.038,29 EUR\nUSt: 197,27 EUR\nBrutto: 1.235,56 EUR"
    )


def test_extraktion_brutto_arithmetisch_bestaetigt() -> None:
    text = _text_mit_allen_feldern()
    roh = _antwort("1.038,29", "197,27", "1.235,56", "15.03.2024", "2024-001")
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert "Brutto: 1.235,56" in findings[0].detail
    assert "15.03.2024" in findings[0].detail


def test_extraktion_detail_enthaelt_brutto_nicht_betrag() -> None:
    """Detail sagt 'Brutto:' – run_eval.py parst es als betrag-Feld."""
    text = "Netto: 128,00 USt: 24,32 Brutto: 152,32"
    roh = _antwort("128,00", "24,32", "152,32")
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert "Brutto:" in findings[0].detail
    assert "Betrag:" not in findings[0].detail


def test_extraktion_ref_enthaelt_beleg_rel() -> None:
    text = "Netto: 84,03 USt: 15,97 Brutto: 100,00"
    roh = _antwort("84,03", "15,97", "100,00")
    findings = _extrahiere("ordner/rechnung.pdf", text, _MockLlm(roh))
    assert findings[0].refs[0].id == "ordner/rechnung.pdf"


# ---------------------------------------------------------------------------
# _extrahiere(): Betrag nicht eindeutig
# ---------------------------------------------------------------------------

def test_extraktion_nur_brutto_keine_arithmetik() -> None:
    """Nur brutto, kein netto/ust → nicht als Brutto gewertet."""
    text = "Rechnungsbetrag: 500,00 EUR"
    roh = _antwort("", "", "500,00")
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert findings[0].severity == "pruefen"
    assert "nicht eindeutig" in findings[0].detail


def test_extraktion_arithmetik_falsch_pruefen() -> None:
    """128 + 24 = 152 ≠ 160 → Betrag nicht eindeutig."""
    text = "Netto: 128,00 USt: 24,00 Brutto: 160,00"
    roh = _antwort("128,00", "24,00", "160,00")
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert findings[0].severity == "pruefen"
    assert "Arithmetik" in findings[0].detail


def test_extraktion_betrag_nicht_eindeutig_detail_enthaelt_netto_ust() -> None:
    """Detail enthält Netto/USt/Brutto für Diagnose (Punkt 4 Anforderung)."""
    text = "Netto: 128,00 USt: 24,00 Brutto: 160,00"
    roh = _antwort("128,00", "24,00", "160,00")
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert "Netto: 128,00" in findings[0].detail
    assert "USt: 24,00" in findings[0].detail
    assert "Brutto: 160,00" in findings[0].detail


def test_extraktion_brutto_netto_verwechslung_klassischer_fall() -> None:
    """LLM gibt nur netto als brutto (klassischer Fehler aus dem Eval).

    128,00 (netto) + 0 (ust leer) → nicht eindeutig.
    """
    text = "Netto 128,00 EUR\nUSt 24,32 EUR\nGesamt 152,32 EUR"
    # LLM verwechselt: brutto=128.00 (netto-Wert), netto+ust leer
    roh = _antwort("", "", "128,00")
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert findings[0].severity == "pruefen"
    assert "nicht eindeutig" in findings[0].detail


# ---------------------------------------------------------------------------
# _extrahiere(): Fehlerfälle
# ---------------------------------------------------------------------------

def test_extraktion_llm_keine_antwort() -> None:
    findings = _extrahiere("test.pdf", "Text", _MockLlm(None))
    assert findings[0].severity == "pruefen"
    assert "LLM-Extraktion fehlgeschlagen" in findings[0].title


def test_extraktion_invalides_json() -> None:
    findings = _extrahiere("test.pdf", "Text", _MockLlm("KEIN JSON"))
    assert findings[0].severity == "pruefen"


def test_extraktion_guard_brutto_nicht_im_text() -> None:
    text = "Netto: 128,00 USt: 24,32"
    roh = _antwort("128,00", "24,32", "99999,00")
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert findings[0].severity == "pruefen"
    assert "Guard fehlgeschlagen" in findings[0].detail
    assert "brutto" in findings[0].detail


def test_extraktion_guard_datum_nicht_im_text() -> None:
    text = "Netto: 128,00 USt: 24,32 Brutto: 152,32 Nr. 2024-001"
    roh = _antwort("128,00", "24,32", "152,32", "01.01.1990", "2024-001")
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert findings[0].severity == "pruefen"
    assert "datum" in findings[0].detail


def test_extraktion_alle_felder_leer_ergibt_pruefen() -> None:
    text = "Unlesbarer Text"
    roh = _antwort("", "", "", "", "")
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert findings[0].severity == "pruefen"


def test_extraktion_nur_datum_nummer_kein_betrag() -> None:
    """Wenn nur datum/nummer extrahiert aber kein Betrag → info (kein Betrag)."""
    text = "Rechnung 2024-001 vom 15.03.2024"
    roh = _antwort("", "", "", "15.03.2024", "2024-001")
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert findings[0].severity == "info"
    assert "kein Betrag" in findings[0].title


# ---------------------------------------------------------------------------
# Injection-Fixture
# ---------------------------------------------------------------------------

def test_injection_in_belegtext_kein_absturz() -> None:
    """Skill läuft mit Injection-Inhalt ohne Absturz oder Exception."""
    fixture_path = Path(__file__).parent / "fixtures" / "beleg_injection.txt"
    injection_text = fixture_path.read_text(encoding="utf-8")

    # Echte Werte aus dem Fixture-Text (netto+ust+brutto vorhanden)
    roh = _antwort("1.974,79", "375,21", "2.350,00", "22.08.2024", "2024-0815")
    findings = _extrahiere("injection.txt", injection_text, _MockLlm(roh))

    assert len(findings) >= 1
    assert all(f.rule == "beleg-extraktion" for f in findings)
    assert findings[0].severity == "info"
    assert "2.350,00" in findings[0].detail


def test_injection_halluzinierter_wert_wird_geblockt() -> None:
    """Werte die nicht im Belegtext vorkommen → Guard feuert."""
    fixture_path = Path(__file__).parent / "fixtures" / "beleg_injection.txt"
    injection_text = fixture_path.read_text(encoding="utf-8")

    roh = _antwort("7777,77", "0,00", "7777,77", "31.12.1899", "ZZZZZZ-9999")
    findings = _extrahiere("injection.txt", injection_text, _MockLlm(roh))

    guard_findings = [f for f in findings if "Guard fehlgeschlagen" in f.detail]
    assert len(guard_findings) >= 1


# ---------------------------------------------------------------------------
# run(): Vollständige Integration
# ---------------------------------------------------------------------------

def test_run_unlesbar_beleg_erzeugt_finding() -> None:
    text = "Netto: 420,17 USt: 79,83 Brutto: 500,00\nRechnung 2024-001"
    b = _beleg(text=text, alle=[])
    roh = _antwort("420,17", "79,83", "500,00", "", "2024-001")
    findings = run(_ctx([b]), _MockLlm(roh))
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert findings[0].rule == "beleg-extraktion"


def test_run_mehrere_unlesbare_belege_je_ein_finding() -> None:
    belege = [
        _beleg("a.pdf", text="Netto 420,17 USt 79,83 Brutto 500,00", alle=[]),
        _beleg("b.pdf", text="Rechnungsbetrag 750,00", alle=[]),
    ]
    roh_a = _antwort("420,17", "79,83", "500,00")
    # Für b liefert der Mock dieselbe Antwort – Werte aus a nicht in b → pruefen
    findings = run(_ctx(belege), _MockLlm(roh_a))
    assert len(findings) == 2


# ---------------------------------------------------------------------------
# Parametrisierte Brutto/Arithmetik-Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text, netto, ust, brutto, erwartet_ok",
    [
        # Korrekte Arithmetik, alle Werte im Text → info
        ("Netto: 128,00 USt: 24,32 Brutto: 152,32", "128,00", "24,32", "152,32", True),
        # EN-Format im Text
        ("Netto: 128.00 Ust: 24.32 Brutto: 152.32", "128.00", "24.32", "152.32", True),
        # Brutto-Wert nicht im Text → Guard
        ("Netto: 128,00 USt: 24,32 Summe: 300,00", "128,00", "24,32", "9999,00", False),
        # Arithmetik falsch → Betrag nicht eindeutig
        ("Netto: 128,00 USt: 24,00 Brutto: 160,00", "128,00", "24,00", "160,00", False),
        # Nur brutto, kein netto/ust → nicht eindeutig
        ("Rechnungsbetrag: 500,00 EUR", "", "", "500,00", False),
    ],
)
def test_brutto_arithmetik_parametrisiert(
    text: str, netto: str, ust: str, brutto: str, erwartet_ok: bool
) -> None:
    roh = _antwort(netto, ust, brutto)
    findings = _extrahiere("test.pdf", text, _MockLlm(roh))
    assert len(findings) == 1
    if erwartet_ok:
        assert findings[0].severity == "info"
        assert "Brutto:" in findings[0].detail
    else:
        assert findings[0].severity == "pruefen"
