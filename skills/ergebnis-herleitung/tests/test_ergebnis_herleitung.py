"""Tests für skills/ergebnis-herleitung/check.py."""
from __future__ import annotations

import importlib.util
from decimal import Decimal as D
from pathlib import Path as _P
from typing import Any

_spec = importlib.util.spec_from_file_location("_ergebnis_herleitung", _P(__file__).parent.parent / "check.py")
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run = _mod.run  # type: ignore[attr-defined]

from fibu.contracts import Konto


def _guv_konto(nr: str, per_s: D, per_h: D, ytd_s: D, ytd_h: D) -> Konto:
    saldo = ytd_h - ytd_s
    return Konto(nr=nr, name=f"Konto {nr}", eb=D(0),
                 per_soll=per_s, per_haben=per_h,
                 ytd_soll=ytd_s, ytd_haben=ytd_h, saldo=saldo)


def test_ohne_befund(make_context: Any) -> None:
    # GuV-Konto 4000: Monat +1000 H, kumuliert +8000 H → Ergebnis 1000 / 8000
    ctx = make_context(
        sus={"4000": _guv_konto("4000", D(0), D(1000), D(0), D(8000))},
        bwa={"Vorläufiges Ergebnis": (D(1000), D(8000))},
    )
    assert run(ctx) == []


def test_monatsergebnis_falsch(make_context: Any) -> None:
    ctx = make_context(
        sus={"4000": _guv_konto("4000", D(0), D(1000), D(0), D(8000))},
        bwa={"Vorläufiges Ergebnis": (D(2000), D(8000))},  # BWA zu hoch
    )
    findings = run(ctx)
    assert any(f.severity == "fehler" and "Monatsergebnis" in f.title for f in findings)
    assert any(f.calc is not None for f in findings)


def test_jahresergebnis_falsch(make_context: Any) -> None:
    ctx = make_context(
        sus={"4000": _guv_konto("4000", D(0), D(1000), D(0), D(8000))},
        bwa={"Vorläufiges Ergebnis": (D(1000), D(9000))},  # kum. zu hoch
    )
    findings = run(ctx)
    assert any(f.severity == "fehler" and "Jahresergebnis" in f.title for f in findings)


def test_keine_guv_konten(make_context: Any) -> None:
    # Nur Bilanzkonto (Klasse 1) → keine GuV-Konten → pruefen-Befund
    ctx = make_context(
        sus={"1200": _guv_konto("1200", D(0), D(0), D(0), D(0))},
        bwa={"Vorläufiges Ergebnis": (D(0), D(0))},
    )
    findings = run(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "pruefen"
    assert findings[0].title == "Ergebnisherleitung nicht möglich"


def test_bwa_ergebniszeile_fehlt(make_context: Any) -> None:
    ctx = make_context(
        sus={"4000": _guv_konto("4000", D(0), D(1000), D(0), D(8000))},
        bwa={},  # keine Ergebniszeile
    )
    findings = run(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "pruefen"
