"""Unit-Tests für src/fibu/ingest/__init__.py – _from_legacy Konverter."""
from __future__ import annotations

from decimal import Decimal as D
from pathlib import Path
from unittest.mock import MagicMock

from fibu.ingest import _from_legacy


def _legacy_konto(nr: str, name: str = "K") -> MagicMock:
    k = MagicMock()
    k.nr, k.name = nr, name
    k.eb = k.per_soll = k.per_haben = k.ytd_soll = k.ytd_haben = k.saldo = D(0)
    return k


def _legacy_page(text: str = "") -> MagicMock:
    p = MagicMock()
    p.text = text
    return p


def _make_legacy_a(**overrides) -> MagicMock:  # type: ignore[no-untyped-def]
    a = MagicMock()
    a.source = Path("test.pdf")
    a.year = 2024
    a.month = 8
    a.created = "31.08.2024"
    a.pages = []
    a.page_types = {}
    a.bwa = {}
    a.wgroups = []
    a.sus = {}
    a.sus_total = {}
    a.opos = []
    a.opos_totals = {}
    a.entwicklung = {}
    a.entw_months = []
    a.ustva = {}
    a.ustva_zahllast = None
    a.ustva_datum = ""
    a.jahreskonten = []
    a.rueckfragen = []
    a.letter_amount = None
    a.ocr_pages = []
    a.warnings = []
    for k, v in overrides.items():
        setattr(a, k, v)
    return a


def test_from_legacy_basis() -> None:
    legacy = _make_legacy_a()
    a = _from_legacy(legacy)
    assert a.source == "test.pdf"
    assert a.year == 2024
    assert a.month == 8
    assert a.page_texts == []


def test_from_legacy_sus() -> None:
    legacy = _make_legacy_a(sus={"4000": _legacy_konto("4000", "Umsatz")})
    a = _from_legacy(legacy)
    assert "4000" in a.sus
    assert a.sus["4000"].name == "Umsatz"


def test_from_legacy_page_texts() -> None:
    legacy = _make_legacy_a(pages=[_legacy_page("Seite 1"), _legacy_page("Seite 2")])
    a = _from_legacy(legacy)
    assert a.page_texts == ["Seite 1", "Seite 2"]


def test_from_legacy_ustva() -> None:
    legacy = _make_legacy_a(ustva={"81": {"base": D(10000), "tax": D(1900)}})
    a = _from_legacy(legacy)
    assert a.ustva["81"].base == D(10000)
    assert a.ustva["81"].tax == D(1900)
