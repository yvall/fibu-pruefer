"""Gesamtvergleich: Legacy-Pfad ↔ neuer Skills-Pfad.

Prüft, dass beide Pfade für denselben Periodenordner
(a) dieselben Befunde (Schwere, Titel, Detail),
(b) dasselbe Monats- und Jahresergebnis aus der BWA und
(c) dieselben Ergebnisaussage-Status liefern.

Ausführung:
    FIBU_GOLDEN_DIR="/pfad/zum/ordner" pytest tests/integration -v
"""
from __future__ import annotations

import difflib
import json
import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def golden_dir() -> Path:
    d = os.environ.get("FIBU_GOLDEN_DIR")
    if not d:
        pytest.skip("FIBU_GOLDEN_DIR nicht gesetzt – Gesamtvergleich übersprungen")
    return Path(d)


@pytest.fixture(scope="module")
def legacy_run(golden_dir: Path):  # type: ignore[no-untyped-def]
    from legacy.fibu_pruefer.pipeline import run  # type: ignore[import]
    return run(golden_dir)


@pytest.fixture(scope="module")
def new_run(golden_dir: Path):  # type: ignore[no-untyped-def]
    from fibu.ingest import load_context
    from fibu.skills_runtime import run_skills

    ctx = load_context(golden_dir)
    results = run_skills(ctx, skills_dir=Path("skills"))
    return ctx, results


# ---------------------------------------------------------------------------
# Normalisierung
# ---------------------------------------------------------------------------

def _normalize_legacy(results):  # type: ignore[no-untyped-def]
    """Legacy CheckResult-Liste → sortierte {severity, title, detail}-Liste."""
    rows = []
    for r in results:
        for f in r.findings:
            if not f.title:
                continue  # leere Pseudo-Findings ignorieren
            rows.append({"severity": f.severity, "title": f.title, "detail": f.detail})
    return sorted(rows, key=lambda x: (x["severity"], x["title"], x["detail"]))


def _normalize_new(results):  # type: ignore[no-untyped-def]
    """SkillResult-Liste → sortierte {severity, title, detail}-Liste."""
    rows = []
    for r in results:
        for f in r.findings:
            if not f.title:
                continue
            rows.append({"severity": f.severity, "title": f.title, "detail": f.detail})
    return sorted(rows, key=lambda x: (x["severity"], x["title"], x["detail"]))


def _diff_msg(expected, actual, label: str) -> str:
    if expected == actual:
        return ""
    only_exp = [f for f in expected if f not in actual]
    only_act = [f for f in actual if f not in expected]
    exp_lines = json.dumps(expected, ensure_ascii=False, indent=2).splitlines()
    act_lines = json.dumps(actual, ensure_ascii=False, indent=2).splitlines()
    diff = "\n".join(
        difflib.unified_diff(exp_lines, act_lines, fromfile="legacy", tofile="neu", lineterm="")
    )
    parts = [f"\n{label}: {len(only_exp)} nur Legacy, {len(only_act)} nur Neu"]
    if only_exp:
        parts.append(f"\nNur Legacy ({len(only_exp)}):")
        parts.extend(f"  - [{f['severity'].upper()}] {f['title'][:100]}" for f in only_exp[:20])
    if only_act:
        parts.append(f"\nNur Neu ({len(only_act)}):")
        parts.extend(f"  + [{f['severity'].upper()}] {f['title'][:100]}" for f in only_act[:20])
    parts.append("\nDiff (erste 60 Zeilen):\n" + "\n".join(diff.splitlines()[:60]))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_befunde_identisch(legacy_run, new_run) -> None:  # type: ignore[no-untyped-def]
    """Beide Pfade liefern dieselben Befunde (Schwere, Titel, Detail)."""
    _, new_results = new_run
    expected = _normalize_legacy(legacy_run.results)
    actual = _normalize_new(new_results)
    msg = _diff_msg(expected, actual, "Befundvergleich")
    assert expected == actual, msg


def test_bwa_ergebnis_identisch(legacy_run, new_run) -> None:  # type: ignore[no-untyped-def]
    """Monats- und Jahresergebnis stimmen zwischen beiden Pfaden überein."""
    ctx, _ = new_run
    legacy_a = legacy_run.auswertung
    new_a = ctx.auswertung

    for label in ("Vorläufiges Ergebnis", "Betriebsergebnis", "Ergebnis vor Steuern"):
        legacy_val = legacy_a.bwa.get(label)
        new_val = new_a.bwa.get(label)
        assert legacy_val == new_val, (
            f"{label}: Legacy {legacy_val} ≠ Neu {new_val}"
        )


def test_ergebnisaussage_status(legacy_run, new_run) -> None:  # type: ignore[no-untyped-def]
    """Die Statusampel aller Ergebnisaussagen stimmt überein."""
    from fibu.report import ergebnisaussage
    from legacy.fibu_pruefer.report import ergebnisaussage as legacy_ea  # type: ignore[import]

    ctx, new_results = new_run
    legacy_a = legacy_run.auswertung
    legacy_results = legacy_run.results

    legacy_aussagen = {frage: status for frage, _, status in legacy_ea(legacy_a, legacy_results)}
    new_aussagen = {frage: status for frage, _, status in ergebnisaussage(ctx.auswertung, new_results)}

    diffs = []
    for frage, leg_st in legacy_aussagen.items():
        # Frage im neuen Pfad über Kurzform (erster Teil bis "?") finden
        short = frage.split("?")[0]
        new_st = next((v for k, v in new_aussagen.items() if short in k), None)
        if new_st is None:
            diffs.append(f"  Frage fehlt im neuen Pfad: {short!r}")
        elif new_st != leg_st:
            diffs.append(f"  Statusunterschied bei {short[:60]!r}: Legacy={leg_st!r}, Neu={new_st!r}")

    assert not diffs, "Ergebnisaussage-Status weicht ab:\n" + "\n".join(diffs)
