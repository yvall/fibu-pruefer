"""Tests für skills/belege-abgleich/check.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path as _P
from typing import Any

_spec = importlib.util.spec_from_file_location("_belege_abgleich", _P(__file__).parent.parent / "check.py")
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run = _mod.run  # type: ignore[attr-defined]


def test_keine_belege(make_context: Any) -> None:
    ctx = make_context()
    findings = run(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "pruefen"
    assert "Keine Belege" in findings[0].title


def test_leere_belege_liste(make_context: Any) -> None:
    ctx = make_context()
    assert ctx.belege == []
    findings = run(ctx)
    # Thin Wrapper gibt "Keine Belege" zurück, wenn Liste leer
    assert any(f.rule == "belege-abgleich" for f in findings)
