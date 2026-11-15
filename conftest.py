"""Gemeinsame Test-Hilfsfunktionen für Unit-Tests und Skill-Tests.

make_auswertung und make_context sind Fixture-Factories und stehen in allen
Tests unter tests/ und skills/ zur Verfügung.

Verwendung in Skill-Tests (je ein Positiv- und ein Negativ-Test):

    from decimal import Decimal as D

    def test_ohne_befund(make_context):
        ctx = make_context(bwa={"Umsatzerlöse": (D("10000"), D("80000")), ...})
        assert run(ctx) == []

    def test_mit_befund(make_context):
        ctx = make_context(bwa={"Umsatzerlöse": (D("10000"), D("80000")),
                                 "Gesamtleistung": (D("9000"), D("80000"))})
        findings = run(ctx)
        assert any(f.severity == "fehler" for f in findings)
"""
from __future__ import annotations

from typing import Any

import pytest

from fibu.contracts import Auswertung, Context


@pytest.fixture
def make_auswertung() -> Any:
    """Fixture-Factory: liefert eine Funktion, die minimale Auswertung-Objekte baut.

    Nur angegebene Felder werden gesetzt; alle anderen bleiben auf Pydantic-Defaults.
    """

    def _make(**overrides: Any) -> Auswertung:
        defaults: dict[str, Any] = {"source": "test.pdf", "year": 2024, "month": 8}
        defaults.update(overrides)
        return Auswertung(**defaults)

    return _make


@pytest.fixture
def make_context(make_auswertung: Any) -> Any:
    """Fixture-Factory: liefert eine Funktion, die einen minimalen Context baut."""

    def _make(**auswertung_overrides: Any) -> Context:
        return Context(auswertung=make_auswertung(**auswertung_overrides))

    return _make
