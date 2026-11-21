"""Tests für skills/rueckfrage-entwurf/check.py – Schritt 3e-2."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from fibu.contracts import Auswertung, Context, Finding
from fibu.llm.null import NullLlmClient

_spec = importlib.util.spec_from_file_location(
    "_rueckfrage_entwurf", Path(__file__).parent.parent / "check.py"
)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

run = _mod.run  # type: ignore[attr-defined]
_entwurf_deterministisch = _mod._entwurf_deterministisch  # type: ignore[attr-defined]


def _ctx(befunde: list[Finding] | None = None) -> Context:
    return Context(
        auswertung=Auswertung(source="test.pdf", year=2024, month=8),
        befunde=befunde or [],
    )


def _f(rule: str, severity: str = "fehler", title: str = "Testbefund") -> Finding:
    return Finding(rule=rule, severity=severity, title=title, detail="Testdetail")


class TestEntwurfDeterministisch:
    def test_negativ_keine_befunde(self) -> None:
        assert _entwurf_deterministisch([]) == []

    def test_negativ_nur_info_befunde(self) -> None:
        befunde = [_f("bwa-rechenwege", "info", "Hinweis")]
        assert _entwurf_deterministisch(befunde) == []

    def test_positiv_ein_fehler(self) -> None:
        befunde = [_f("bwa-rechenwege", "fehler", "Differenz 1.234,56 €")]
        result = _entwurf_deterministisch(befunde)
        assert len(result) == 1
        f = result[0]
        assert f.rule == "rueckfrage-entwurf"
        assert f.severity == "info"
        assert "bwa-rechenwege" in f.title
        assert "1 Befund" in f.title
        assert "Differenz 1.234,56 €" in f.detail
        assert "bitte prüfen" in f.detail

    def test_positiv_pruefen_severity(self) -> None:
        befunde = [_f("opos-pruefung", "pruefen", "Posten offen")]
        result = _entwurf_deterministisch(befunde)
        assert len(result) == 1
        assert "Posten offen" in result[0].detail

    def test_drei_themengruppen(self) -> None:
        befunde = [
            _f("bwa-rechenwege", "fehler", "Fehler A"),
            _f("bwa-rechenwege", "pruefen", "Auffälligkeit B"),
            _f("opos-pruefung", "pruefen", "Offener Posten"),
            _f("summen-salden", "fehler", "Saldenabweichung"),
        ]
        result = _entwurf_deterministisch(befunde)
        assert len(result) == 3
        titles = [f.title for f in result]
        assert any("bwa-rechenwege" in t for t in titles)
        assert any("opos-pruefung" in t for t in titles)
        assert any("summen-salden" in t for t in titles)

    def test_zaehlung_im_titel_plural(self) -> None:
        befunde = [
            _f("bwa-rechenwege", "fehler", "A"),
            _f("bwa-rechenwege", "pruefen", "B"),
            _f("bwa-rechenwege", "fehler", "C"),
        ]
        result = _entwurf_deterministisch(befunde)
        assert len(result) == 1
        assert "3 Befunde" in result[0].title

    def test_zaehlung_im_titel_singular(self) -> None:
        befunde = [_f("bwa-rechenwege", "fehler", "Einzelbefund")]
        result = _entwurf_deterministisch(befunde)
        assert "1 Befund)" in result[0].title

    def test_eigene_befunde_nicht_re_gruppiert(self) -> None:
        befunde = [
            _f("rueckfrage-entwurf", "fehler", "Eigenes Finding"),
            _f("bwa-rechenwege", "fehler", "Echtes Finding"),
        ]
        result = _entwurf_deterministisch(befunde)
        assert len(result) == 1
        assert "bwa-rechenwege" in result[0].title

    def test_detail_enthaelt_muster(self) -> None:
        befunde = [_f("summen-salden", "fehler", "Konto 1200 Differenz 500,00 €")]
        result = _entwurf_deterministisch(befunde)
        assert result[0].detail.startswith("Zu summen-salden:")
        assert "Konto 1200 Differenz 500,00 €" in result[0].detail
        assert "– bitte prüfen und den Sachverhalt mitteilen." in result[0].detail

    def test_mehrere_findings_je_gruppe_in_detail(self) -> None:
        befunde = [
            _f("opos-pruefung", "pruefen", "Posten A"),
            _f("opos-pruefung", "fehler", "Posten B"),
        ]
        result = _entwurf_deterministisch(befunde)
        assert len(result) == 1
        assert "Posten A" in result[0].detail
        assert "Posten B" in result[0].detail

    def test_output_severity_immer_info(self) -> None:
        befunde = [
            _f("bwa-rechenwege", "fehler", "X"),
            _f("summen-salden", "pruefen", "Y"),
        ]
        result = _entwurf_deterministisch(befunde)
        assert all(f.severity == "info" for f in result)

    def test_output_rule_immer_rueckfrage_entwurf(self) -> None:
        befunde = [_f("kosten-deckung", "fehler", "Z")]
        result = _entwurf_deterministisch(befunde)
        assert all(f.rule == "rueckfrage-entwurf" for f in result)


class TestRun:
    def test_run_mit_null_llm_client(self) -> None:
        llm = NullLlmClient()
        ctx = _ctx([_f("bwa-rechenwege", "fehler", "Differenz")])
        result = run(ctx, llm)
        assert len(result) == 1
        assert result[0].severity == "info"

    def test_run_keine_befunde(self) -> None:
        llm = NullLlmClient()
        ctx = _ctx([])
        assert run(ctx, llm) == []

    def test_run_detail_enthaelt_titel(self) -> None:
        llm = NullLlmClient()
        ctx = _ctx([_f("kosten-deckung", "pruefen", "Beleg fehlt 500,00 €")])
        result = run(ctx, llm)
        assert any("Beleg fehlt 500,00 €" in f.detail for f in result)

    def test_run_info_befunde_werden_ignoriert(self) -> None:
        llm = NullLlmClient()
        ctx = _ctx([
            _f("bwa-rechenwege", "info", "Nur Hinweis"),
            _f("summen-salden", "fehler", "Echter Fehler"),
        ])
        result = run(ctx, llm)
        assert len(result) == 1
        assert "summen-salden" in result[0].title
