"""Paritätstest: check_summen_salden (Legacy) ↔ skills/summen-salden (Skill)."""
from __future__ import annotations

import os
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest
from migration_parity import assert_migration_parity, load_skill_run  # type: ignore[import]  # Pfad via conftest.py

from fibu.contracts import Auswertung, Context, Konto
from legacy.fibu_pruefer.checks import check_summen_salden  # type: ignore[import]

_skill_run = load_skill_run("summen-salden")


# ---------------------------------------------------------------------------
# Testdaten
# ---------------------------------------------------------------------------

def _sus_korrekt() -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Synthetische Paritätstests
# ---------------------------------------------------------------------------

def test_parity_keine_abweichung(make_context: Any) -> None:
    ctx = make_context(**_sus_korrekt())
    assert_migration_parity(check_summen_salden, _skill_run, ctx)


def test_parity_saldo_falsch(make_context: Any) -> None:
    sus = dict(_sus_korrekt()["sus"])
    sus["4000"] = Konto(nr="4000", name="Umsatzerlöse",
                        eb=D(0), per_soll=D(0), per_haben=D(10000),
                        ytd_soll=D(0), ytd_haben=D(80000), saldo=D(-79000))
    ctx = make_context(sus=sus)
    assert_migration_parity(check_summen_salden, _skill_run, ctx)


def test_parity_soll_haben_ungleich(make_context: Any) -> None:
    sus = dict(_sus_korrekt()["sus"])
    sus["4000"] = Konto(nr="4000", name="Umsatzerlöse",
                        eb=D(0), per_soll=D(500), per_haben=D(10000),
                        ytd_soll=D(0), ytd_haben=D(80000), saldo=D(-80000))
    ctx = make_context(sus=sus)
    assert_migration_parity(check_summen_salden, _skill_run, ctx)


def test_parity_personenkonten(make_context: Any) -> None:
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
    assert_migration_parity(check_summen_salden, _skill_run, ctx)


def test_parity_sus_leer(make_context: Any) -> None:
    ctx = make_context(sus={})
    assert_migration_parity(check_summen_salden, _skill_run, ctx)


def test_parity_summenzeile(make_context: Any) -> None:
    data = _sus_korrekt()
    data["sus_total"] = {"per_soll": D(9000)}
    ctx = make_context(**data)
    assert_migration_parity(check_summen_salden, _skill_run, ctx)


# ---------------------------------------------------------------------------
# Echtdaten-Paritätstest
# ---------------------------------------------------------------------------

@pytest.fixture
def golden_dir() -> Path:
    d = os.environ.get("FIBU_GOLDEN_DIR")
    if not d:
        pytest.skip("FIBU_GOLDEN_DIR nicht gesetzt – Echtdaten-Paritätstest übersprungen")
    return Path(d)


def test_parity_echtdaten(golden_dir: Path) -> None:
    """Legacy und Skill liefern für das echte SuS dieselben Befunde."""
    from legacy.fibu_pruefer.parser import load_auswertung  # type: ignore[import]
    from legacy.fibu_pruefer.pipeline import find_bwa_pdf  # type: ignore[import]

    pdf = find_bwa_pdf(golden_dir)
    if pdf is None:
        pytest.skip("Kein BWA-PDF in FIBU_GOLDEN_DIR")

    legacy_a = load_auswertung(pdf)
    ctx = Context(
        auswertung=Auswertung(
            source=str(pdf),
            year=legacy_a.year,
            month=legacy_a.month,
            sus={
                nr: Konto(
                    nr=nr,
                    name=k.name,
                    eb=k.eb,
                    per_soll=k.per_soll,
                    per_haben=k.per_haben,
                    ytd_soll=k.ytd_soll,
                    ytd_haben=k.ytd_haben,
                    saldo=k.saldo,
                )
                for nr, k in legacy_a.sus.items()
            },
            sus_total=legacy_a.sus_total,
        )
    )
    assert_migration_parity(check_summen_salden, _skill_run, ctx)
