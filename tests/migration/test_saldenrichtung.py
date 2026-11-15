"""Paritätstest: check_kontenrichtung (Legacy) ↔ skills/saldenrichtung (Skill)."""
from __future__ import annotations

import os
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest
from migration_parity import assert_migration_parity, load_skill_run  # type: ignore[import]  # Pfad via conftest.py

from fibu.contracts import Auswertung, Context, Konto
from legacy.fibu_pruefer.checks import check_kontenrichtung  # type: ignore[import]

_skill_run = load_skill_run("saldenrichtung")


def _k(nr: str, saldo: D, per_s: D = D(0), per_h: D = D(0)) -> Konto:
    return Konto(nr=nr, name=f"Konto {nr}", eb=D(0),
                 per_soll=per_s, per_haben=per_h,
                 ytd_soll=D(0), ytd_haben=D(0), saldo=saldo)


def test_parity_korrekte_richtung(make_context: Any) -> None:
    ctx = make_context(sus={"4000": _k("4000", D(-1000))})
    assert_migration_parity(check_kontenrichtung, _skill_run, ctx)


def test_parity_ungewoehnlicher_saldo(make_context: Any) -> None:
    ctx = make_context(sus={"4000": _k("4000", D(500))})
    assert_migration_parity(check_kontenrichtung, _skill_run, ctx)


def test_parity_negative_monatssumme(make_context: Any) -> None:
    ctx = make_context(sus={"4000": _k("4000", D(-1000), per_s=D(-100))})
    assert_migration_parity(check_kontenrichtung, _skill_run, ctx)


def test_parity_personenkonto_falsche_seite(make_context: Any) -> None:
    ctx = make_context(sus={"10001": _k("10001", D(-500))})
    assert_migration_parity(check_kontenrichtung, _skill_run, ctx)


def test_parity_skip_konto(make_context: Any) -> None:
    ctx = make_context(sus={"3820": _k("3820", D(5000))})
    assert_migration_parity(check_kontenrichtung, _skill_run, ctx)


def test_parity_sus_leer(make_context: Any) -> None:
    ctx = make_context(sus={})
    assert_migration_parity(check_kontenrichtung, _skill_run, ctx)


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
    ctx = Context(
        auswertung=Auswertung(
            source=str(pdf),
            year=legacy_a.year,
            month=legacy_a.month,
            sus={
                nr: Konto(nr=nr, name=k.name, eb=k.eb,
                          per_soll=k.per_soll, per_haben=k.per_haben,
                          ytd_soll=k.ytd_soll, ytd_haben=k.ytd_haben,
                          saldo=k.saldo)
                for nr, k in legacy_a.sus.items()
            },
        )
    )
    assert_migration_parity(check_kontenrichtung, _skill_run, ctx)
