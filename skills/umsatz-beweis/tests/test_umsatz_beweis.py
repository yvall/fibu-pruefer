"""Tests für skills/umsatz-beweis/check.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path as _P
from typing import Any

_spec = importlib.util.spec_from_file_location("_umsatz_beweis", _P(__file__).parent.parent / "check.py")
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run = _mod.run  # type: ignore[attr-defined]


def test_keine_erloesekonten(make_context: Any) -> None:
    # Ohne Erlöse 44xx → kein Befund
    ctx = make_context(sus={})
    assert run(ctx) == []


def test_keine_belege_keine_opos(make_context: Any) -> None:
    from decimal import Decimal as D

    from fibu.contracts import Konto
    k = Konto(nr="4400", name="Erlöse", eb=D(0), per_soll=D(0), per_haben=D(1000),
              ytd_soll=D(0), ytd_haben=D(8000), saldo=D(-8000))
    ctx = make_context(sus={"4400": k})
    findings = run(ctx)
    # Skill läuft durch, findet aber keine Belege → Differenz
    assert all(f.rule == "umsatz-beweis" for f in findings)
