"""Paritätstest: check_vormonat (Legacy) ↔ skills/vormonat-fortschreibung (Skill)."""
from __future__ import annotations

import os
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest
from migration_parity import assert_migration_parity, load_skill_run  # type: ignore[import]  # Pfad via conftest.py

from fibu.contracts import Auswertung, Context, Konto
from legacy.fibu_pruefer.checks import check_vormonat  # type: ignore[import]

_skill_run = load_skill_run("vormonat-fortschreibung")


# ---------------------------------------------------------------------------
# Testdaten
# ---------------------------------------------------------------------------

def _a(**kw: Any) -> Auswertung:
    defaults: dict[str, Any] = {"source": "test.pdf", "year": 2024, "month": 8}
    defaults.update(kw)
    return Auswertung(**defaults)


def _ctx(a: Auswertung, p: Auswertung | None = None) -> Context:
    return Context(auswertung=a, prev=p)


# ---------------------------------------------------------------------------
# Synthetische Paritätstests (duck-typing ✓ – alle Felder identisch)
# ---------------------------------------------------------------------------

def test_parity_ohne_prev() -> None:
    ctx = _ctx(_a())
    assert_migration_parity(lambda a: check_vormonat(a, ctx.prev), _skill_run, ctx)


def test_parity_falscher_vormonat() -> None:
    ctx = _ctx(_a(month=8, year=2024), _a(month=6, year=2024))
    assert_migration_parity(lambda a: check_vormonat(a, ctx.prev), _skill_run, ctx)


def test_parity_bwa_fortschreibung_ok() -> None:
    ctx = _ctx(
        _a(month=8, year=2024, bwa={"Umsatzerlöse": (D(500), D(1500))}),
        _a(month=7, year=2024, bwa={"Umsatzerlöse": (D(0), D(1000))}),
    )
    assert_migration_parity(lambda a: check_vormonat(a, ctx.prev), _skill_run, ctx)


def test_parity_bwa_fortschreibung_abweichung() -> None:
    ctx = _ctx(
        _a(month=8, year=2024, bwa={"Umsatzerlöse": (D(500), D(1600))}),
        _a(month=7, year=2024, bwa={"Umsatzerlöse": (D(0), D(1000))}),
    )
    assert_migration_parity(lambda a: check_vormonat(a, ctx.prev), _skill_run, ctx)


def test_parity_konto_geaendert() -> None:
    k_aktuell = Konto(nr="4000", name="Umsatz", eb=D(0),
                      per_soll=D(0), per_haben=D(500),
                      ytd_soll=D(0), ytd_haben=D(1200), saldo=D(-1200))
    k_vormonat = Konto(nr="4000", name="Umsatz", eb=D(0),
                       per_soll=D(0), per_haben=D(0),
                       ytd_soll=D(0), ytd_haben=D(1000), saldo=D(-1000))
    ctx = _ctx(
        _a(month=8, year=2024, sus={"4000": k_aktuell}),
        _a(month=7, year=2024, sus={"4000": k_vormonat}),
    )
    assert_migration_parity(lambda a: check_vormonat(a, ctx.prev), _skill_run, ctx)


# ---------------------------------------------------------------------------
# Echtdaten-Paritätstest
# ---------------------------------------------------------------------------

@pytest.fixture
def golden_dir() -> Path:
    d = os.environ.get("FIBU_GOLDEN_DIR")
    if not d:
        pytest.skip("FIBU_GOLDEN_DIR nicht gesetzt")
    return Path(d)


def test_parity_echtdaten(golden_dir: Path) -> None:
    """Parity mit beiden PDFs im BWA-Ordner (Vormonat + Berichtsmonat)."""
    from legacy.fibu_pruefer.parser import load_auswertung  # type: ignore[import]
    from legacy.fibu_pruefer.pipeline import list_bwa_pdfs  # type: ignore[import]

    pdfs = list_bwa_pdfs(golden_dir)
    if len(pdfs) < 2:
        pytest.skip("Weniger als 2 PDFs im BWA-Ordner – Vormonat nicht verfügbar")

    legacy_p = load_auswertung(pdfs[-2][1])  # Vormonat
    legacy_a = load_auswertung(pdfs[-1][1])  # Berichtsmonat

    def _sus(la: Any) -> dict[str, Konto]:
        return {
            nr: Konto(nr=nr, name=k.name, eb=k.eb,
                      per_soll=k.per_soll, per_haben=k.per_haben,
                      ytd_soll=k.ytd_soll, ytd_haben=k.ytd_haben, saldo=k.saldo)
            for nr, k in la.sus.items()
        }

    contracts_p = Auswertung(
        source=str(pdfs[-2][1]), year=legacy_p.year, month=legacy_p.month,
        bwa=legacy_p.bwa, sus=_sus(legacy_p),
        entwicklung=legacy_p.entwicklung, entw_months=legacy_p.entw_months,
        ocr_pages=legacy_p.ocr_pages, page_types=legacy_p.page_types,
    )
    contracts_a = Auswertung(
        source=str(pdfs[-1][1]), year=legacy_a.year, month=legacy_a.month,
        bwa=legacy_a.bwa, sus=_sus(legacy_a),
        entwicklung=legacy_a.entwicklung, entw_months=legacy_a.entw_months,
        ocr_pages=legacy_a.ocr_pages, page_types=legacy_a.page_types,
    )
    ctx = Context(auswertung=contracts_a, prev=contracts_p)
    assert_migration_parity(lambda a: check_vormonat(a, ctx.prev), _skill_run, ctx)
