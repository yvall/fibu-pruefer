"""Paritätstest: check_bwa_arithmetik (Legacy) ↔ skills/bwa-rechenwege (Skill).

Synthetische Tests laufen immer. Echtdaten-Test läuft nur mit FIBU_GOLDEN_DIR.
"""
from __future__ import annotations

import os
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest
from migration_parity import assert_migration_parity, load_skill_run  # type: ignore[import]  # Pfad via conftest.py

from fibu.contracts import Auswertung, Context
from legacy.fibu_pruefer.checks import check_bwa_arithmetik  # type: ignore[import]

_skill_run = load_skill_run("bwa-rechenwege")


# ---------------------------------------------------------------------------
# Testdaten
# ---------------------------------------------------------------------------

def _bwa_korrekt() -> dict[str, Any]:
    """Minimal-BWA mit korrekten Rechenwegen für alle neun Formeln."""
    return {
        "bwa": {
            "Umsatzerlöse":         (D("10000.00"), D("80000.00")),
            "Best.Verdg. FE/UE":    (D("0.00"),     D("0.00")),
            "Akt.Eigenleistungen":  (D("0.00"),     D("0.00")),
            "Gesamtleistung":       (D("10000.00"), D("80000.00")),
            "Mat./Wareneinkauf":    (D("2000.00"),  D("16000.00")),
            "Rohertrag":            (D("8000.00"),  D("64000.00")),
            "So. betr. Erlöse":     (D("0.00"),     D("0.00")),
            "Betriebl. Rohertrag":  (D("8000.00"),  D("64000.00")),
            "Personalkosten":       (D("3000.00"),  D("24000.00")),
            "Raumkosten":           (D("500.00"),   D("4000.00")),
            "Betriebl. Steuern":    (D("0.00"),     D("0.00")),
            "Versich./Beiträge":    (D("100.00"),   D("800.00")),
            "Besondere Kosten":     (D("0.00"),     D("0.00")),
            "Fahrzeugko. (o. St)":  (D("200.00"),   D("1600.00")),
            "Werbe-/Reisekosten":   (D("100.00"),   D("800.00")),
            "Kosten Warenabgabe":   (D("0.00"),     D("0.00")),
            "Abschreibungen":       (D("100.00"),   D("800.00")),
            "Reparatur/Instandh.":  (D("0.00"),     D("0.00")),
            "Sonstige Kosten":      (D("0.00"),     D("0.00")),
            "Gesamtkosten":         (D("4000.00"),  D("32000.00")),
            "Betriebsergebnis":     (D("4000.00"),  D("32000.00")),
            "Zinsaufwand":          (D("0.00"),     D("0.00")),
            "Sonst. neutr. Aufw":   (D("0.00"),     D("0.00")),
            "Neutraler Aufwand":    (D("0.00"),     D("0.00")),
            "Zinserträge":          (D("0.00"),     D("0.00")),
            "Sonst. neutr. Ertr":   (D("0.00"),     D("0.00")),
            "Verr. kalk. Kosten":   (D("0.00"),     D("0.00")),
            "Neutraler Ertrag":     (D("0.00"),     D("0.00")),
            "Kontenkl. unbesetzt":  (D("0.00"),     D("0.00")),
            "Ergebnis vor Steuern": (D("4000.00"),  D("32000.00")),
            "Steuern Eink.u.Ertr":  (D("0.00"),     D("0.00")),
            "Vorläufiges Ergebnis": (D("4000.00"),  D("32000.00")),
        }
    }


# ---------------------------------------------------------------------------
# Synthetische Paritätstests (laufen immer)
# ---------------------------------------------------------------------------

def test_parity_keine_abweichung(make_context: Any) -> None:
    """Korrektes BWA → beide liefern keine Befunde."""
    ctx = make_context(**_bwa_korrekt())
    assert_migration_parity(check_bwa_arithmetik, _skill_run, ctx)


def test_parity_vorlaeufigergebnis_falsch(make_context: Any) -> None:
    """Vorläufiges Ergebnis um 10 € zu hoch → je ein Befund pro Periode, identisch."""
    data = _bwa_korrekt()
    bwa = dict(data["bwa"])
    bwa["Vorläufiges Ergebnis"] = (D("4010.00"), D("32010.00"))
    data["bwa"] = bwa
    ctx = make_context(**data)
    assert_migration_parity(check_bwa_arithmetik, _skill_run, ctx)


def test_parity_gesamtleistung_falsch(make_context: Any) -> None:
    """Gesamtleistung falsch → Kaskadeneffekt auf Rohertrag; beide müssen identisch sein."""
    data = _bwa_korrekt()
    bwa = dict(data["bwa"])
    bwa["Gesamtleistung"] = (D("10010.00"), D("80010.00"))
    data["bwa"] = bwa
    ctx = make_context(**data)
    assert_migration_parity(check_bwa_arithmetik, _skill_run, ctx)


def test_parity_bwa_leer(make_context: Any) -> None:
    """Leeres BWA → beide liefern 'BWA nicht lesbar'."""
    ctx = make_context(bwa={})
    assert_migration_parity(check_bwa_arithmetik, _skill_run, ctx)


def test_parity_nur_teilzeilen(make_context: Any) -> None:
    """BWA enthält nur einen Teil der Zeilen → fehlende werden übersprungen."""
    ctx = make_context(
        bwa={
            "Umsatzerlöse":         (D("5000.00"), D("40000.00")),
            "Best.Verdg. FE/UE":    (D("0.00"),    D("0.00")),
            "Akt.Eigenleistungen":  (D("0.00"),    D("0.00")),
            "Gesamtleistung":       (D("5000.00"), D("40000.00")),
        }
    )
    assert_migration_parity(check_bwa_arithmetik, _skill_run, ctx)


# ---------------------------------------------------------------------------
# Echtdaten-Paritätstest (überspringen ohne FIBU_GOLDEN_DIR)
# ---------------------------------------------------------------------------

@pytest.fixture
def golden_dir() -> Path:
    d = os.environ.get("FIBU_GOLDEN_DIR")
    if not d:
        pytest.skip("FIBU_GOLDEN_DIR nicht gesetzt – Echtdaten-Paritätstest übersprungen")
    return Path(d)


def test_parity_echtdaten(golden_dir: Path) -> None:
    """Legacy und Skill liefern für das echte BWA-PDF dieselben Befunde."""
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
        )
    )
    assert_migration_parity(check_bwa_arithmetik, _skill_run, ctx)
