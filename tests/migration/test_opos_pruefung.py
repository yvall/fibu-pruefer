"""Paritätstest: check_opos (Legacy) ↔ skills/opos-pruefung (Skill)."""
from __future__ import annotations

import os
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest
from migration_parity import assert_migration_parity, load_skill_run  # type: ignore[import]  # Pfad via conftest.py

from fibu.contracts import Auswertung, Context, Konto, OposItem
from legacy.fibu_pruefer.checks import check_opos  # type: ignore[import]

_skill_run = load_skill_run("opos-pruefung")


def _opos(konto: str, soll: D, belegnr: str = "R001", faellig: str = "") -> OposItem:
    return OposItem(konto=konto, konto_name=f"Kto {konto}", belegnr=belegnr,
                    datum="01.08.2024", faellig=faellig, gegenkonto="4000",
                    soll=soll, haben=D(0))


def test_parity_leer(make_context: Any) -> None:
    ctx = make_context(opos=[], sus={}, created="31.08.2024", year=2024, month=8)
    assert_migration_parity(check_opos, _skill_run, ctx)


def test_parity_saldo_abweichung(make_context: Any) -> None:
    ctx = make_context(
        opos=[_opos("10001", D(1000))],
        sus={"10001": Konto(nr="10001", name="K", eb=D(0),
                            per_soll=D(0), per_haben=D(0),
                            ytd_soll=D(0), ytd_haben=D(0), saldo=D(500))},
        created="31.08.2024", year=2024, month=8,
    )
    assert_migration_parity(check_opos, _skill_run, ctx)


def test_parity_doppelte_nummer(make_context: Any) -> None:
    ctx = make_context(
        opos=[_opos("10001", D(500), "R001"), _opos("10001", D(500), "R001")],
        sus={}, created="31.08.2024", year=2024, month=8,
    )
    assert_migration_parity(check_opos, _skill_run, ctx)


def test_parity_ueberfaellig(make_context: Any) -> None:
    ctx = make_context(
        opos=[_opos("10001", D(1000), faellig="01.01.2024")],
        sus={}, created="31.08.2024", year=2024, month=8,
    )
    assert_migration_parity(check_opos, _skill_run, ctx)


@pytest.fixture
def golden_dir() -> Path:
    d = os.environ.get("FIBU_GOLDEN_DIR")
    if not d:
        pytest.skip("FIBU_GOLDEN_DIR nicht gesetzt")
    return Path(d)


def test_parity_echtdaten(golden_dir: Path) -> None:
    from legacy.fibu_pruefer.parser import load_auswertung  # type: ignore[import]
    from legacy.fibu_pruefer.pipeline import find_bwa_pdf  # type: ignore[import]

    pdf = find_bwa_pdf(golden_dir)
    if pdf is None:
        pytest.skip("Kein BWA-PDF in FIBU_GOLDEN_DIR")
    legacy_a = load_auswertung(pdf)
    ctx = Context(auswertung=Auswertung(
        source=str(pdf), year=legacy_a.year, month=legacy_a.month,
        created=legacy_a.created,
        opos=[OposItem(konto=it.konto, konto_name=it.konto_name, belegnr=it.belegnr,
                       datum=it.datum, faellig=it.faellig, gegenkonto=it.gegenkonto,
                       soll=it.soll, haben=it.haben, text=it.text)
              for it in legacy_a.opos],
        sus={nr: Konto(nr=nr, name=k.name, eb=k.eb, per_soll=k.per_soll,
                       per_haben=k.per_haben, ytd_soll=k.ytd_soll,
                       ytd_haben=k.ytd_haben, saldo=k.saldo)
             for nr, k in legacy_a.sus.items()},
    ))
    assert_migration_parity(check_opos, _skill_run, ctx)
