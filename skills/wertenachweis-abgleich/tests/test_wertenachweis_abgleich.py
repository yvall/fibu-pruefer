"""Tests für skills/wertenachweis-abgleich/check.py."""
from __future__ import annotations

import importlib.util
from decimal import Decimal as D
from pathlib import Path as _P
from typing import Any

_spec = importlib.util.spec_from_file_location("_wertenachweis_abgleich", _P(__file__).parent.parent / "check.py")
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run = _mod.run  # type: ignore[attr-defined]

from fibu.contracts import Konto, WGroup, WKonto


def _wg(zeile: str, name: str, bwa_per: D, bwa_ytd: D, kontos: list[WKonto]) -> WGroup:
    return WGroup(zeile=zeile, name=name, bwa_per=bwa_per, bwa_ytd=bwa_ytd, kontos=kontos)


def test_ohne_befund(make_context: Any) -> None:
    ctx = make_context(
        wgroups=[_wg("10", "Umsatzerlöse", D(1000), D(8000),
                     [WKonto(nr="4000", sh="H", name="Umsatz", per=D(1000), ytd=D(8000))])],
        bwa={"Umsatzerlöse": (D(1000), D(8000))},
        sus={"4000": Konto(nr="4000", name="Umsatz", eb=D(0),
                           per_soll=D(0), per_haben=D(1000),
                           ytd_soll=D(0), ytd_haben=D(8000), saldo=D(-8000))},
    )
    assert run(ctx) == []


def test_konten_ungleich_bwa_wert(make_context: Any) -> None:
    ctx = make_context(
        wgroups=[_wg("10", "Umsatzerlöse", D(2000), D(8000),
                     [WKonto(nr="4000", sh="H", name="Umsatz", per=D(1000), ytd=D(8000))])],
        bwa={},
        sus={},
    )
    findings = run(ctx)
    assert any("Konten ≠ BWA-Wert (Monat)" in f.title for f in findings)


def test_konto_ungleich_sus(make_context: Any) -> None:
    ctx = make_context(
        wgroups=[_wg("10", "X", D(500), D(500),
                     [WKonto(nr="4000", sh="H", name="Kto", per=D(500), ytd=D(500))])],
        bwa={},
        sus={"4000": Konto(nr="4000", name="Kto", eb=D(0),
                           per_soll=D(0), per_haben=D(1000),  # per_move=1000, aber WK=500
                           ytd_soll=D(0), ytd_haben=D(1000), saldo=D(-1000))},
    )
    findings = run(ctx)
    assert any("Summen/Salden" in f.title for f in findings)


def test_keine_wgroups(make_context: Any) -> None:
    ctx = make_context(wgroups=[], bwa={}, sus={})
    assert run(ctx) == []
