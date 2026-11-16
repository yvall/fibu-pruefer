"""Tests für skills/kosten-deckung/check.py."""
from __future__ import annotations

import importlib.util
from decimal import Decimal as D
from pathlib import Path as _P
from typing import Any

_spec = importlib.util.spec_from_file_location("_kosten_deckung", _P(__file__).parent.parent / "check.py")
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run = _mod.run  # type: ignore[attr-defined]

from fibu.contracts import Konto


def test_keine_kostenstellen(make_context: Any) -> None:
    ctx = make_context(sus={})
    assert run(ctx) == []


def test_kosten_ohne_belege(make_context: Any) -> None:
    k = Konto(nr="6300", name="Büromaterial", eb=D(0),
              per_soll=D(500), per_haben=D(0),
              ytd_soll=D(500), ytd_haben=D(0), saldo=D(500))
    ctx = make_context(sus={"6300": k})
    findings = run(ctx)
    # Mit Kosten aber ohne Belege: Differenz-Finding
    assert any(f.rule == "kosten-deckung" for f in findings)
