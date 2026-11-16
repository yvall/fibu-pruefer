"""Paritätstest: check_klaerung (Legacy) ↔ skills/klaerungsliste (Skill).

Ohne Klärungsliste (ctx.klaerung=[]) gibt die Skill sofort [] zurück;
kein Legacy-Aufruf nötig. Echtdaten-Test: nur wenn FIBU_GOLDEN_DIR gesetzt
und eine .xlsx-Klärungsliste vorhanden ist.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from migration_parity import assert_migration_parity, load_skill_run  # type: ignore[import]

from fibu.contracts import Auswertung, BelegRecord, Context, JahresEintrag, JahresKonto, KlaerRow, Konto

_skill_run = load_skill_run("klaerungsliste")


def test_parity_keine_klaerung(make_context) -> None:  # type: ignore[no-untyped-def]
    ctx = make_context()
    # Leere klaerung → Skill gibt [] zurück; kein Legacy-Aufruf nötig
    assert _skill_run(ctx) == []


@pytest.fixture
def golden_dir() -> Path:
    d = os.environ.get("FIBU_GOLDEN_DIR")
    if not d:
        pytest.skip("FIBU_GOLDEN_DIR nicht gesetzt")
    return Path(d)


def test_parity_echtdaten(golden_dir: Path) -> None:
    from legacy.fibu_pruefer.belege import check_klaerung, load_klaerung, scan  # type: ignore[import]
    from legacy.fibu_pruefer.parser import load_auswertung  # type: ignore[import]
    from legacy.fibu_pruefer.pipeline import find_bwa_pdf  # type: ignore[import]

    legacy_rows = load_klaerung(golden_dir)
    if not legacy_rows:
        pytest.skip("Keine Klärungsliste im Periodenordner")

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
    klaerung_rows = [
        KlaerRow(text=r.text, monat=r.monat, betrag=r.betrag, kommentar=r.kommentar)
        for r in legacy_rows
    ]
    jahreskonten = [
        JahresKonto(
            nr=jk.nr, name=jk.name, eb=jk.eb, saldo=jk.saldo,
            jvz_soll=jk.jvz_soll, jvz_haben=jk.jvz_haben,
            entries=[JahresEintrag(datum=e["datum"], text=e["text"],
                                   soll=e["soll"], haben=e["haben"])
                     for e in jk.entries],
        )
        for jk in legacy_a.jahreskonten
    ]
    ctx = Context(
        auswertung=Auswertung(
            source=str(pdf), year=legacy_a.year, month=legacy_a.month,
            jahreskonten=jahreskonten,
            sus={nr: Konto(nr=nr, name=k.name, eb=k.eb, per_soll=k.per_soll,
                           per_haben=k.per_haben, ytd_soll=k.ytd_soll,
                           ytd_haben=k.ytd_haben, saldo=k.saldo)
                 for nr, k in legacy_a.sus.items()},
        ),
        belege=belegrecords,
        klaerung=klaerung_rows,
    )
    assert_migration_parity(
        lambda a: check_klaerung(a, legacy_belege, legacy_rows, None),
        _skill_run, ctx,
        legacy_auswertung=legacy_a,
    )
