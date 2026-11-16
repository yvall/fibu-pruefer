"""Paritätstest: check_entwicklung (Legacy) ↔ skills/entwicklung-ausreisser (Skill)."""
from __future__ import annotations

import os
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest
from migration_parity import assert_migration_parity, load_skill_run  # type: ignore[import]  # Pfad via conftest.py

from fibu.contracts import Auswertung, Context
from legacy.fibu_pruefer.checks import check_entwicklung  # type: ignore[import]

_skill_run = load_skill_run("entwicklung-ausreisser")


def test_parity_keine_entwicklung(make_context: Any) -> None:
    ctx = make_context(entwicklung={})
    assert_migration_parity(check_entwicklung, _skill_run, ctx)


def test_parity_ohne_abweichung(make_context: Any) -> None:
    ctx = make_context(
        entwicklung={"Umsatzerlöse": [D(1000)] * 13},
        bwa={"Umsatzerlöse": (D(1000), D(12000))},
        entw_months=[f"M{i}" for i in range(13)],
        month=12,
    )
    assert_migration_parity(check_entwicklung, _skill_run, ctx)


def test_parity_monatswert_abweichung(make_context: Any) -> None:
    ctx = make_context(
        entwicklung={"Umsatzerlöse": [D(1000)] * 13},
        bwa={"Umsatzerlöse": (D(2000), D(13000))},
        entw_months=[f"M{i}" for i in range(13)],
        month=12,
    )
    assert_migration_parity(check_entwicklung, _skill_run, ctx)


def test_parity_ausreisser(make_context: Any) -> None:
    ctx = make_context(
        entwicklung={"Personalkosten": [D(1000)] * 12 + [D(50000)]},
        bwa={},
        entw_months=[f"M{i}" for i in range(13)],
        month=12,
    )
    assert_migration_parity(check_entwicklung, _skill_run, ctx)


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
        bwa=legacy_a.bwa, entwicklung=legacy_a.entwicklung,
        entw_months=legacy_a.entw_months, ocr_pages=legacy_a.ocr_pages,
        page_types=legacy_a.page_types,
    ))
    assert_migration_parity(check_entwicklung, _skill_run, ctx)
