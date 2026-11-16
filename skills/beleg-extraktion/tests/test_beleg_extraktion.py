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

from fibu.contracts import Auswertung, BelegRecord, Context

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
    """Mock-LLM für Tests."""

    def __init__(self, antwort: str | None) -> None:
        self._antwort = antwort
        self.modell = "mock"
        self.aufrufe: list[str] = []

    def modell_fuer(self, skill_id: str) -> str:
        return self.modell

    def generiere(
        self,
        prompt: str,
        json_schema: dict[str, Any] | None = None,
        *,
        modell: str = "",
    ) -> str | None:
        self.aufrufe.append(prompt)
        return self._antwort


# ---------------------------------------------------------------------------
# Guard _wert_in_text
# ---------------------------------------------------------------------------

def test_guard_leerer_wert_immer_true() -> None:
    assert _wert_in_text("", "beliebiger Text") is True
    assert _wert_in_text("  ", "beliebiger Text") is True


def test_guard_direkte_uebereinstimmung() -> None:
    assert _wert_in_text("1.234,56", "Betrag: 1.234,56 EUR") is True


def test_guard_de_format_in_en_text() -> None:
    # "1.234,56" → DE→EN "1234.56" → findet "1234.56" im Text
    assert _wert_in_text("1.234,56", "Total: 1234.56 USD") is True


def test_guard_en_format_in_de_text() -> None:
    # Ziffern-Fallback: "1234.56" → Ziffern "123456" ≥5 → sucht in Ziffern von Text
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
    a = _parse_llm_antwort('{"betrag":"1.234,56","datum":"15.03.2024","nummer":"2024-001"}')
    assert a is not None
    assert a.betrag == "1.234,56"
    assert a.datum == "15.03.2024"


def test_parse_mit_erklaertext_fallback() -> None:
    # Modell stellt Text voran – json.loads-Fallback
    roh = 'Hier ist die Antwort:\n{"betrag":"500,00","datum":"","nummer":"RG-42"}'
    a = _parse_llm_antwort(roh)
    assert a is not None
    assert a.betrag == "500,00"


def test_parse_leere_felder() -> None:
    a = _parse_llm_antwort('{"betrag":"","datum":"","nummer":""}')
    assert a is not None
    assert a.betrag == ""


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
# _extrahiere(): Erfolgsfall
# ---------------------------------------------------------------------------

def test_extraktion_positiv_info_finding() -> None:
    text = "Rechnung 2024-001\n15.03.2024\nBetrag: 1.234,56 EUR"
    antwort = '{"betrag":"1.234,56","datum":"15.03.2024","nummer":"2024-001"}'
    findings = _extrahiere("test.pdf", text, _MockLlm(antwort))
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert findings[0].rule == "beleg-extraktion"
    assert "1.234,56" in findings[0].detail
    assert "15.03.2024" in findings[0].detail


def test_extraktion_ref_enthaelt_beleg_rel() -> None:
    text = "Betrag: 100,00 EUR"
    antwort = '{"betrag":"100,00","datum":"","nummer":""}'
    findings = _extrahiere("ordner/rechnung.pdf", text, _MockLlm(antwort))
    assert len(findings) == 1
    assert findings[0].refs[0].id == "ordner/rechnung.pdf"


# ---------------------------------------------------------------------------
# _extrahiere(): Fehlerfälle
# ---------------------------------------------------------------------------

def test_extraktion_llm_keine_antwort() -> None:
    findings = _extrahiere("test.pdf", "Text", _MockLlm(None))
    assert len(findings) == 1
    assert findings[0].severity == "pruefen"
    assert "LLM-Extraktion fehlgeschlagen" in findings[0].title


def test_extraktion_invalides_json() -> None:
    findings = _extrahiere("test.pdf", "Text", _MockLlm("KEIN JSON"))
    assert len(findings) == 1
    assert findings[0].severity == "pruefen"


def test_extraktion_guard_betrag_nicht_im_text() -> None:
    text = "Rechnung 2024-001\nBetrag: 1.234,56 EUR"
    antwort = '{"betrag":"99999,00","datum":"","nummer":""}'
    findings = _extrahiere("test.pdf", text, _MockLlm(antwort))
    assert len(findings) == 1
    assert findings[0].severity == "pruefen"
    assert "Guard fehlgeschlagen" in findings[0].detail
    assert "betrag" in findings[0].detail


def test_extraktion_guard_datum_nicht_im_text() -> None:
    text = "Rechnung Nr. 2024-001\nBetrag: 500,00 EUR"
    antwort = '{"betrag":"500,00","datum":"01.01.1990","nummer":"2024-001"}'
    findings = _extrahiere("test.pdf", text, _MockLlm(antwort))
    assert len(findings) == 1
    assert findings[0].severity == "pruefen"
    assert "datum" in findings[0].detail


def test_extraktion_alle_felder_leer_ergibt_pruefen() -> None:
    text = "Unlesbarer Text ohne erkennbare Daten"
    antwort = '{"betrag":"","datum":"","nummer":""}'
    findings = _extrahiere("test.pdf", text, _MockLlm(antwort))
    assert len(findings) == 1
    assert findings[0].severity == "pruefen"


# ---------------------------------------------------------------------------
# Injection-Fixture
# ---------------------------------------------------------------------------

def test_injection_in_belegtext_kein_absturz() -> None:
    """Skill läuft mit Injection-Inhalt im Belegtext ohne Absturz oder Exception."""
    fixture_path = Path(__file__).parent / "fixtures" / "beleg_injection.txt"
    injection_text = fixture_path.read_text(encoding="utf-8")

    # Mock-LLM gibt die echten Werte aus dem Text zurück (kein Injection-Erfolg)
    antwort = '{"betrag":"2.350,00","datum":"22.08.2024","nummer":"2024-0815"}'
    findings = _extrahiere("injection.txt", injection_text, _MockLlm(antwort))

    assert len(findings) >= 1
    assert all(f.rule == "beleg-extraktion" for f in findings)
    # Guard: echte Werte kommen im Text vor → info-Finding
    assert findings[0].severity == "info"


def test_injection_halluzinierter_wert_wird_geblockt() -> None:
    """LLM halluziniert Werte, die nirgends im Belegtext vorkommen → Guard feuert.

    Das Mock-LLM gibt Werte zurück, die nicht im Originaltext der Fixture stehen.
    Damit prüfen wir, dass der Guard unabhängig vom Injektionsversuch greift.
    """
    fixture_path = Path(__file__).parent / "fixtures" / "beleg_injection.txt"
    injection_text = fixture_path.read_text(encoding="utf-8")

    # Werte, die sicher nicht in der Fixture vorkommen
    antwort = '{"betrag":"7777,77","datum":"31.12.1899","nummer":"ZZZZZZ-9999"}'
    findings = _extrahiere("injection.txt", injection_text, _MockLlm(antwort))

    guard_findings = [f for f in findings if "Guard fehlgeschlagen" in f.detail]
    assert len(guard_findings) >= 1


# ---------------------------------------------------------------------------
# run(): Vollständige Integration mit unlesbarem Beleg
# ---------------------------------------------------------------------------

def test_run_unlesbar_beleg_erzeugt_finding() -> None:
    b = _beleg(text="Rechnung 2024-001\n500,00 EUR", alle=[])
    antwort = '{"betrag":"500,00","datum":"","nummer":"2024-001"}'
    findings = run(_ctx([b]), _MockLlm(antwort))
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert findings[0].rule == "beleg-extraktion"


def test_run_mehrere_unlesbare_belege() -> None:
    belege = [
        _beleg("a.pdf", text="500,00 EUR", alle=[]),
        _beleg("b.pdf", text="750,00 EUR", alle=[]),
    ]
    antwort = '{"betrag":"500,00","datum":"","nummer":""}'
    findings = run(_ctx(belege), _MockLlm(antwort))
    assert len(findings) == 2


@pytest.mark.parametrize(
    "text, betrag, erwartet_ok",
    [
        ("Rechnung\n1.234,56 EUR", "1.234,56", True),   # DE-Format direkt
        ("Invoice\n1234.56 USD", "1234.56", True),        # EN-Format direkt
        ("Total: 1234.56 EUR", "1.234,56", True),         # DE im EN-Text (via Ziffern)
        ("Gesamt: 1.234,56 EUR", "1234.56", True),        # EN im DE-Text (via Ziffern)
        ("Betrag: 500,00 EUR", "9999,00", False),          # Halluzination → Guard
    ],
)
def test_guard_betragsformate_parametrisiert(
    text: str, betrag: str, erwartet_ok: bool
) -> None:
    antwort = f'{{"betrag":"{betrag}","datum":"","nummer":""}}'
    findings = _extrahiere("test.pdf", text, _MockLlm(antwort))
    assert len(findings) == 1
    if erwartet_ok:
        assert findings[0].severity == "info"
    else:
        assert findings[0].severity == "pruefen"
