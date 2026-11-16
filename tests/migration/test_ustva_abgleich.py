"""Paritätstest: check_ustva (Legacy) ↔ skills/ustva-abgleich (Skill).

Nur Echtdaten-Test: legacy ustva ist dict[str,dict], contracts UstvaKz ist Pydantic.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from migration_parity import assert_migration_parity, load_skill_run  # type: ignore[import]  # Pfad via conftest.py

from fibu.contracts import Auswertung, Context, Konto, UstvaKz
from legacy.fibu_pruefer.checks import check_ustva  # type: ignore[import]

_skill_run = load_skill_run("ustva-abgleich")


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
        sus={nr: Konto(nr=nr, name=k.name, eb=k.eb, per_soll=k.per_soll,
                       per_haben=k.per_haben, ytd_soll=k.ytd_soll,
                       ytd_haben=k.ytd_haben, saldo=k.saldo)
             for nr, k in legacy_a.sus.items()},
        ustva={kz: UstvaKz(base=v.get("base"), tax=v.get("tax"))
               for kz, v in legacy_a.ustva.items()},
        ustva_zahllast=legacy_a.ustva_zahllast,
        ustva_datum=legacy_a.ustva_datum,
        letter_amount=legacy_a.letter_amount,
        page_texts=[p.text for p in legacy_a.pages],
    ))
    assert_migration_parity(check_ustva, _skill_run, ctx, legacy_auswertung=legacy_a)
