"""Tests für skills/ustva-abgleich/check.py."""
from __future__ import annotations

import importlib.util
from decimal import Decimal as D
from pathlib import Path as _P
from typing import Any

_spec = importlib.util.spec_from_file_location("_ustva_abgleich", _P(__file__).parent.parent / "check.py")
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run = _mod.run  # type: ignore[attr-defined]

from fibu.contracts import UstvaKz


def test_ohne_ustva(make_context: Any) -> None:
    ctx = make_context(ustva={})
    findings = run(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "pruefen"
    assert "nicht gefunden" in findings[0].title


def test_zahllast_falsch(make_context: Any) -> None:
    # Kz.81=1000, Kz.66=0, Kz.83=500 → Zahllast=1000≠500
    ctx = make_context(ustva={
        "81": UstvaKz(base=None, tax=D(1000)),
        "66": UstvaKz(tax=D(0)),
        "83": UstvaKz(tax=D(500)),
    })
    findings = run(ctx)
    assert any("Zahllast falsch" in f.title for f in findings)


def test_zahllast_korrekt(make_context: Any) -> None:
    # Kz.81=1000, Kz.66=200, Kz.83=800 → Zahllast=800 ✓
    ctx = make_context(ustva={
        "81": UstvaKz(base=None, tax=D(1000)),
        "66": UstvaKz(tax=D(200)),
        "83": UstvaKz(tax=D(800)),
    })
    findings = [f for f in run(ctx) if "Zahllast" in f.title]
    assert findings == []
