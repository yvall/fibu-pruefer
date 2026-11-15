"""Paritätstest: check_ergebnis_aus_konten (Legacy) ↔ skills/ergebnis-herleitung (Skill)."""
from __future__ import annotations

import os
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest
from migration_parity import assert_migration_parity, load_skill_run  # type: ignore[import]  # Pfad via conftest.py

from fibu.contracts import Auswertung, Context, Konto
from legacy.fibu_pruefer.checks import check_ergebnis_aus_konten  # type: ignore[import]

_skill_run = load_skill_run("ergebnis-herleitung")


def _guv(nr: str, ps: D, ph: D, ys: D, yh: D) -> Konto:
    return Konto(nr=nr, name=f"Konto {nr}", eb=D(0),
                 per_soll=ps, per_haben=ph, ytd_soll=ys, ytd_haben=yh,
                 saldo=yh - ys)


def test_parity_keine_abweichung(make_context: Any) -> None:
    ctx = make_context(
        sus={"4000": _guv("4000", D(0), D(1000), D(0), D(8000))},
        bwa={"Vorläufiges Ergebnis": (D(1000), D(8000))},
    )
    assert_migration_parity(check_ergebnis_aus_konten, _skill_run, ctx)


def test_parity_monatsfehler(make_context: Any) -> None:
    ctx = make_context(
        sus={"4000": _guv("4000", D(0), D(1000), D(0), D(8000))},
        bwa={"Vorläufiges Ergebnis": (D(2000), D(8000))},
    )
    assert_migration_parity(check_ergebnis_aus_konten, _skill_run, ctx)


def test_parity_jahresfehler(make_context: Any) -> None:
    ctx = make_context(
        sus={"4000": _guv("4000", D(0), D(1000), D(0), D(8000))},
        bwa={"Vorläufiges Ergebnis": (D(1000), D(9000))},
    )
    assert_migration_parity(check_ergebnis_aus_konten, _skill_run, ctx)


def test_parity_keine_guv_konten(make_context: Any) -> None:
    ctx = make_context(
        sus={"1200": _guv("1200", D(0), D(0), D(0), D(0))},
        bwa={"Vorläufiges Ergebnis": (D(0), D(0))},
    )
    assert_migration_parity(check_ergebnis_aus_konten, _skill_run, ctx)


def test_parity_bwa_leer(make_context: Any) -> None:
    ctx = make_context(
        sus={"4000": _guv("4000", D(0), D(1000), D(0), D(8000))},
        bwa={},
    )
    assert_migration_parity(check_ergebnis_aus_konten, _skill_run, ctx)


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
            bwa=legacy_a.bwa,
            sus={
                nr: Konto(nr=nr, name=k.name, eb=k.eb,
                          per_soll=k.per_soll, per_haben=k.per_haben,
                          ytd_soll=k.ytd_soll, ytd_haben=k.ytd_haben,
                          saldo=k.saldo)
                for nr, k in legacy_a.sus.items()
            },
        )
    )
    assert_migration_parity(check_ergebnis_aus_konten, _skill_run, ctx)
