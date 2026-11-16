"""Tests für skills/opos-pruefung/check.py."""
from __future__ import annotations

import importlib.util
from decimal import Decimal as D
from pathlib import Path as _P
from typing import Any

_spec = importlib.util.spec_from_file_location("_opos_pruefung", _P(__file__).parent.parent / "check.py")
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run = _mod.run  # type: ignore[attr-defined]

from fibu.contracts import Konto, OposItem


def _opos(konto: str, soll: D, belegnr: str = "R001", faellig: str = "") -> OposItem:
    return OposItem(konto=konto, konto_name=f"Kto {konto}", belegnr=belegnr,
                    datum="01.08.2024", faellig=faellig, gegenkonto="4000",
                    soll=soll, haben=D(0))


def test_ohne_befund(make_context: Any) -> None:
    ctx = make_context(
        opos=[_opos("10001", D(1000))],
        sus={"1200": Konto(nr="1200", name="Debitoren", eb=D(0),
                           per_soll=D(1000), per_haben=D(0),
                           ytd_soll=D(1000), ytd_haben=D(0), saldo=D(1000))},
        created="31.08.2024", year=2024, month=8,
    )
    assert run(ctx) == []


def test_saldo_abweichung(make_context: Any) -> None:
    ctx = make_context(
        opos=[_opos("10001", D(1000))],
        sus={"10001": Konto(nr="10001", name="K", eb=D(0),
                            per_soll=D(0), per_haben=D(0),
                            ytd_soll=D(0), ytd_haben=D(0), saldo=D(500))},
        created="31.08.2024", year=2024, month=8,
    )
    findings = run(ctx)
    assert any(f.severity == "fehler" and "OPOS Konto" in f.title for f in findings)


def test_doppelte_rechnungsnummer(make_context: Any) -> None:
    ctx = make_context(
        opos=[_opos("10001", D(500), "R001"), _opos("10001", D(500), "R001")],
        sus={},
        created="31.08.2024", year=2024, month=8,
    )
    findings = run(ctx)
    assert any("doppelt" in f.title for f in findings)


def test_ueberfaellige_forderung(make_context: Any) -> None:
    ctx = make_context(
        opos=[_opos("10001", D(1000), faellig="01.01.2024")],
        sus={},
        created="31.08.2024", year=2024, month=8,
    )
    findings = run(ctx)
    assert any(f.severity == "pruefen" and "überfällig" in f.title for f in findings)
