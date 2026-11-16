"""Tests für skills/entwicklung-ausreisser/check.py."""
from __future__ import annotations

import importlib.util
from decimal import Decimal as D
from pathlib import Path as _P
from typing import Any

_spec = importlib.util.spec_from_file_location("_entwicklung_ausreisser", _P(__file__).parent.parent / "check.py")
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run = _mod.run  # type: ignore[attr-defined]


def test_ohne_befund(make_context: Any) -> None:
    ctx = make_context(
        entwicklung={"Umsatzerlöse": [D(1000)] * 13},
        bwa={"Umsatzerlöse": (D(1000), D(12000))},
        entw_months=[f"M{i}" for i in range(13)],
        month=12,
    )
    assert run(ctx) == []


def test_keine_entwicklung(make_context: Any) -> None:
    ctx = make_context(entwicklung={})
    findings = run(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "pruefen"
    assert "nicht lesbar" in findings[0].title


def test_monatswert_bwa_abweichung(make_context: Any) -> None:
    ctx = make_context(
        entwicklung={"Umsatzerlöse": [D(1000)] * 13},
        bwa={"Umsatzerlöse": (D(2000), D(13000))},  # BWA zu hoch
        entw_months=[f"M{i}" for i in range(13)],
        month=12,
    )
    findings = run(ctx)
    assert any("Monatswert" in f.title for f in findings)


def test_ausreisser(make_context: Any) -> None:
    # 12 Monate bei 1000, letzter Monat 50000 → Ausreißer
    ctx = make_context(
        entwicklung={"Personalkosten": [D(1000)] * 12 + [D(50000)]},
        bwa={},
        entw_months=[f"M{i}" for i in range(13)],
        month=12,
    )
    findings = run(ctx)
    assert any(f.severity == "info" for f in findings)
