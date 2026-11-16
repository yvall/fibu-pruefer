"""Paritätstest: check_durchlaufend (Legacy) ↔ skills/durchlaufende-posten (Skill).

Nur Echtdaten-Test: legacy JahresKonto.entries ist list[dict], contracts JahresEintrag
ist Pydantic-Model – duck-typing nicht möglich.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from migration_parity import assert_migration_parity, load_skill_run  # type: ignore[import]  # Pfad via conftest.py

from fibu.contracts import Auswertung, Context, JahresEintrag, JahresKonto
from legacy.fibu_pruefer.checks import check_durchlaufend  # type: ignore[import]

_skill_run = load_skill_run("durchlaufende-posten")


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
        jahreskonten=[
            JahresKonto(
                nr=jk.nr, name=jk.name, eb=jk.eb, saldo=jk.saldo,
                jvz_soll=jk.jvz_soll, jvz_haben=jk.jvz_haben,
                entries=[JahresEintrag(datum=e["datum"], text=e["text"],
                                       soll=e["soll"], haben=e["haben"])
                         for e in jk.entries],
            )
            for jk in legacy_a.jahreskonten
        ],
    ))
    assert_migration_parity(check_durchlaufend, _skill_run, ctx, legacy_auswertung=legacy_a)
