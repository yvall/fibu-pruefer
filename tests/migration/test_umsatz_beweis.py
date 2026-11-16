"""Paritätstest: check_umsatz (Legacy) ↔ skills/umsatz-beweis (Skill)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from migration_parity import assert_migration_parity, load_skill_run  # type: ignore[import]

from fibu.contracts import Auswertung, BelegRecord, Context, Konto, OposItem
from legacy.fibu_pruefer.belege import check_umsatz  # type: ignore[import]

_skill_run = load_skill_run("umsatz-beweis")


def test_parity_keine_erloesekonten(make_context) -> None:  # type: ignore[no-untyped-def]
    ctx = make_context(sus={})
    assert_migration_parity(lambda a: check_umsatz(a, []), _skill_run, ctx)


@pytest.fixture
def golden_dir() -> Path:
    d = os.environ.get("FIBU_GOLDEN_DIR")
    if not d:
        pytest.skip("FIBU_GOLDEN_DIR nicht gesetzt")
    return Path(d)


def test_parity_echtdaten(golden_dir: Path) -> None:
    from legacy.fibu_pruefer.belege import scan  # type: ignore[import]
    from legacy.fibu_pruefer.parser import load_auswertung  # type: ignore[import]
    from legacy.fibu_pruefer.pipeline import find_bwa_pdf  # type: ignore[import]

    pdf = find_bwa_pdf(golden_dir)
    if pdf is None:
        pytest.skip("Kein BWA-PDF")
    legacy_a = load_auswertung(pdf)
    legacy_belege = scan(golden_dir)

    belegrecords = [
        BelegRecord(path=str(b.path), rel=b.rel, sha=b.sha, text=b.text,
                    kind=b.kind, brutto=b.brutto, netto=b.netto, alle=b.alle,
                    daten=b.daten, nummern=b.nummern, leistung=b.leistung, ocr=b.ocr)
        for b in legacy_belege
    ]
    sus = {nr: Konto(nr=nr, name=k.name, eb=k.eb, per_soll=k.per_soll,
                     per_haben=k.per_haben, ytd_soll=k.ytd_soll,
                     ytd_haben=k.ytd_haben, saldo=k.saldo)
           for nr, k in legacy_a.sus.items()}
    opos = [OposItem(konto=it.konto, konto_name=it.konto_name, belegnr=it.belegnr,
                     datum=it.datum, faellig=it.faellig, gegenkonto=it.gegenkonto,
                     soll=it.soll, haben=it.haben, text=it.text)
            for it in legacy_a.opos]
    ctx = Context(
        auswertung=Auswertung(
            source=str(pdf), year=legacy_a.year, month=legacy_a.month,
            sus=sus, opos=opos,
        ),
        belege=belegrecords,
    )
    assert_migration_parity(
        lambda a: check_umsatz(a, legacy_belege),
        _skill_run, ctx,
    )
