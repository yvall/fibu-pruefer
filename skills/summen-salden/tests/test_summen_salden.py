"""Tests für skills/summen-salden/check.py."""
from __future__ import annotations

from decimal import Decimal as D
from typing import Any

from check import run  # type: ignore[import]  # Pfad via conftest.py

from fibu.contracts import Konto


def _sus_korrekt() -> dict[str, Any]:
    """Minimal-SuS mit zwei balancierten Sachkonten, keine Personenkonten."""
    return {
        "sus": {
            "4000": Konto(nr="4000", name="Umsatzerlöse",
                          eb=D(0), per_soll=D(0), per_haben=D(10000),
                          ytd_soll=D(0), ytd_haben=D(80000), saldo=D(-80000)),
            "1200": Konto(nr="1200", name="Debitoren",
                          eb=D(0), per_soll=D(10000), per_haben=D(0),
                          ytd_soll=D(80000), ytd_haben=D(0), saldo=D(80000)),
        }
    }


def test_ohne_befund(make_context: Any) -> None:
    ctx = make_context(**_sus_korrekt())
    assert run(ctx) == []


def test_saldo_falsch(make_context: Any) -> None:
    sus = dict(_sus_korrekt()["sus"])
    sus["4000"] = Konto(nr="4000", name="Umsatzerlöse",
                        eb=D(0), per_soll=D(0), per_haben=D(10000),
                        ytd_soll=D(0), ytd_haben=D(80000), saldo=D(-79000))
    ctx = make_context(sus=sus)
    findings = run(ctx)
    assert any(f.severity == "fehler" and "4000" in f.title for f in findings)


def test_soll_haben_ungleich_monat(make_context: Any) -> None:
    sus = dict(_sus_korrekt()["sus"])
    sus["4000"] = Konto(nr="4000", name="Umsatzerlöse",
                        eb=D(0), per_soll=D(500), per_haben=D(10000),
                        ytd_soll=D(0), ytd_haben=D(80000), saldo=D(-80000))
    ctx = make_context(sus=sus)
    findings = run(ctx)
    assert any(f.title == "Soll ≠ Haben im Monat" for f in findings)


def test_personenkonten_ungleich_sammelkonto(make_context: Any) -> None:
    sus = {
        "1200": Konto(nr="1200", name="Debitoren", eb=D(0),
                      per_soll=D(5000), per_haben=D(0),
                      ytd_soll=D(5000), ytd_haben=D(0), saldo=D(5000)),
        "10001": Konto(nr="10001", name="Kunde A", eb=D(0),
                       per_soll=D(5000), per_haben=D(0),
                       ytd_soll=D(5000), ytd_haben=D(0), saldo=D(6000)),
        "4000": Konto(nr="4000", name="Umsatz", eb=D(0),
                      per_soll=D(0), per_haben=D(5000),
                      ytd_soll=D(0), ytd_haben=D(5000), saldo=D(-5000)),
    }
    ctx = make_context(sus=sus)
    findings = run(ctx)
    assert any("Personenkonten ≠ Sammelkonto" in f.title for f in findings)


def test_sus_leer(make_context: Any) -> None:
    ctx = make_context(sus={})
    assert run(ctx) == []


def test_summenzeile_abweichung(make_context: Any) -> None:
    data = _sus_korrekt()
    data["sus_total"] = {"per_soll": D(9000)}  # Konten ergeben 10000, Summenzeile 9000
    ctx = make_context(**data)
    findings = run(ctx)
    assert any(f.severity == "pruefen" and "Summenzeile" in f.title for f in findings)
