"""Tests für skills/durchlaufende-posten/check.py."""
from __future__ import annotations

import importlib.util
from decimal import Decimal as D
from pathlib import Path as _P
from typing import Any

_spec = importlib.util.spec_from_file_location("_durchlaufende_posten", _P(__file__).parent.parent / "check.py")
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run = _mod.run  # type: ignore[attr-defined]

from fibu.contracts import JahresEintrag, JahresKonto


def _jk(nr: str, saldo: D, eb: D, soll: D, haben: D, entries: list[JahresEintrag]) -> JahresKonto:
    return JahresKonto(nr=nr, name=f"Kto {nr}", eb=eb,
                       saldo=saldo, jvz_soll=soll, jvz_haben=haben,
                       entries=entries)


def _e(datum: str, soll: D = D(0), haben: D = D(0), text: str = "Test") -> JahresEintrag:
    return JahresEintrag(datum=datum, text=text, soll=soll, haben=haben)


def test_ohne_befund(make_context: Any) -> None:
    # Ausgeglichenes Jahres­konto, ein Soll gleich einem Haben
    jk = _jk("9900", D(0), D(0), D(500), D(500),
              [_e("15.08.2024", soll=D(500)), _e("20.08.2024", haben=D(500))])
    ctx = make_context(jahreskonten=[jk], created="31.08.2024")
    assert run(ctx) == []


def test_saldo_falsch(make_context: Any) -> None:
    jk = _jk("9900", D(100), D(0), D(500), D(500),
              [_e("15.08.2024", soll=D(500)), _e("20.08.2024", haben=D(500))])
    ctx = make_context(jahreskonten=[jk], created="31.08.2024")
    findings = run(ctx)
    assert any(f.severity == "fehler" and "rechnerisch falsch" in f.title for f in findings)


def test_doppelbuchung(make_context: Any) -> None:
    # Gleicher Eintrag zweimal
    e = _e("15.08.2024", soll=D(500))
    jk = _jk("9900", D(0), D(0), D(1000), D(0), [e, e])
    ctx = make_context(jahreskonten=[jk], created="31.08.2024")
    findings = run(ctx)
    assert any("identische Buchung" in f.title for f in findings)


def test_keine_jahreskonten(make_context: Any) -> None:
    ctx = make_context(jahreskonten=[], created="31.08.2024")
    assert run(ctx) == []
