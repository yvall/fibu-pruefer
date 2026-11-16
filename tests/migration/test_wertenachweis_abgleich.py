"""Paritätstest: check_wertenachweis (Legacy) ↔ skills/wertenachweis-abgleich (Skill).

Synthetische Duck-Typing-Tests entfallen, da legacy WGroup.kontos list[dict] ist,
contracts WGroup.kontos aber list[WKonto]. Nur Echtdaten-Test mit expliziter
legacy_auswertung.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from migration_parity import assert_migration_parity, load_skill_run  # type: ignore[import]  # Pfad via conftest.py

from fibu.contracts import Auswertung, Context, Konto, WGroup, WKonto
from legacy.fibu_pruefer.checks import check_wertenachweis  # type: ignore[import]

_skill_run = load_skill_run("wertenachweis-abgleich")


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
        bwa=legacy_a.bwa,
        wgroups=[
            WGroup(
                zeile=g.zeile, name=g.name, bwa_per=g.bwa_per,
                bwa_ytd=g.bwa_ytd, ocr=g.ocr,
                kontos=[WKonto(nr=k["nr"], sh=k["sh"], name=k["name"],
                               per=k["per"], ytd=k["ytd"])
                        for k in g.kontos],
            )
            for g in legacy_a.wgroups
        ],
        sus={nr: Konto(nr=nr, name=k.name, eb=k.eb, per_soll=k.per_soll,
                       per_haben=k.per_haben, ytd_soll=k.ytd_soll,
                       ytd_haben=k.ytd_haben, saldo=k.saldo)
             for nr, k in legacy_a.sus.items()},
    ))
    assert_migration_parity(check_wertenachweis, _skill_run, ctx, legacy_auswertung=legacy_a)
