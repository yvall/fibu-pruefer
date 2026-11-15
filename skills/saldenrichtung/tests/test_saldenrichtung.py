"""Tests für skills/saldenrichtung/check.py."""
from __future__ import annotations

import importlib.util
from decimal import Decimal as D
from pathlib import Path as _P
from typing import Any

_spec = importlib.util.spec_from_file_location("_saldenrichtung", _P(__file__).parent.parent / "check.py")
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run = _mod.run  # type: ignore[attr-defined]

from fibu.contracts import Konto


def _k(nr: str, saldo: D, per_s: D = D(0), per_h: D = D(0)) -> Konto:
    return Konto(nr=nr, name=f"Konto {nr}", eb=D(0),
                 per_soll=per_s, per_haben=per_h,
                 ytd_soll=D(0), ytd_haben=D(0), saldo=saldo)


def test_ohne_befund(make_context: Any) -> None:
    # Konto 4000 Haben (Klasse 4 erwartet Haben = negativ) → korrekt
    ctx = make_context(sus={"4000": _k("4000", D(-1000))})
    assert run(ctx) == []


def test_ungewoehnlicher_saldo(make_context: Any) -> None:
    # Konto 4000 mit Soll-Saldo (erwartet Haben) → pruefen
    ctx = make_context(sus={"4000": _k("4000", D(500))})
    findings = run(ctx)
    assert any(f.severity == "pruefen" and "ungewöhnlicher" in f.title for f in findings)


def test_saldo_unter_schwelle(make_context: Any) -> None:
    # Saldo < 1,00 € → kein Befund
    ctx = make_context(sus={"4000": _k("4000", D("0.50"))})
    assert run(ctx) == []


def test_negative_monatssumme(make_context: Any) -> None:
    ctx = make_context(sus={"4000": _k("4000", D(-1000), per_s=D(-100), per_h=D(0))})
    findings = run(ctx)
    assert any(f.severity == "info" and "negative Monatssumme" in f.title for f in findings)


def test_personenkonto_falsche_seite(make_context: Any) -> None:
    # Debitor-Personenkonto 10001 mit Haben-Saldo (erwartet Soll)
    ctx = make_context(sus={"10001": _k("10001", D(-500))})
    findings = run(ctx)
    assert any(f.severity == "pruefen" and "Personenkonto" in f.title for f in findings)


def test_skip_konto_kein_befund(make_context: Any) -> None:
    # Konto 3820 ist in der Skip-Liste → kein Richtungs-Befund
    ctx = make_context(sus={"3820": _k("3820", D(5000))})  # Klasse 3 erwartet Haben
    findings = [f for f in run(ctx) if "ungewöhnlicher" in f.title]
    assert findings == []
