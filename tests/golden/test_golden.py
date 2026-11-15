"""Golden-Test: fixiert die Befunde des Legacy-Laufs als Referenz.

Ausführung:
  FIBU_GOLDEN_DIR=/pfad/zum/ordner pytest tests/golden -v     # Vergleich
  FIBU_GOLDEN_DIR=...  FIBU_GOLDEN_UPDATE=1  pytest tests/golden -v  # Referenz neu schreiben

Die Referenzdatei (golden_findings.json) liegt im Periodenordner außerhalb des Repos
und wird nie committet.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from legacy.fibu_pruefer.pipeline import run as legacy_run


@pytest.fixture
def golden_dir() -> Path:
    d = os.environ.get("FIBU_GOLDEN_DIR")
    if not d:
        pytest.skip("FIBU_GOLDEN_DIR nicht gesetzt – Golden-Test übersprungen")
    return Path(d)


def _to_comparable(results: list[Any]) -> list[dict[str, str]]:
    """Wandelt CheckResult-Liste in eine stabile, sortierbare Vergleichsstruktur.

    Verglichen werden: Check-Key, Schweregrad, Titel und Detail (enthält Beträge).
    Sortierung nach (check, severity, title), damit Reihenfolgeänderungen den
    Test nicht fälschlicherweise brechen.
    """
    rows: list[dict[str, str]] = []
    for r in results:
        for f in r.findings:
            rows.append(
                {
                    "check": r.key,
                    "severity": f.severity,
                    "title": f.title,
                    "detail": f.detail,
                }
            )
    return sorted(rows, key=lambda x: (x["check"], x["severity"], x["title"]))


def test_golden_bericht(golden_dir: Path) -> None:
    golden_file = golden_dir / "golden_findings.json"
    update = bool(os.environ.get("FIBU_GOLDEN_UPDATE"))

    result = legacy_run(golden_dir)
    findings = _to_comparable(result.results)

    if update or not golden_file.exists():
        golden_file.write_text(
            json.dumps(findings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        verb = "aktualisiert" if update else "angelegt"
        pytest.skip(f"Referenz {verb}: {golden_file} – bitte erneut ausführen zum Vergleich")

    expected: list[dict[str, str]] = json.loads(golden_file.read_text(encoding="utf-8"))

    if findings != expected:
        only_new = [f for f in findings if f not in expected]
        only_old = [f for f in expected if f not in findings]
        lines = [
            f"Golden-Test fehlgeschlagen: {len(only_new)} neue, {len(only_old)} weggefallene Befunde.",
        ]
        if only_new:
            lines.append(f"\nNeue Befunde ({len(only_new)}):")
            lines.extend(f"  + {r}" for r in only_new[:20])
        if only_old:
            lines.append(f"\nWeggefallene Befunde ({len(only_old)}):")
            lines.extend(f"  - {r}" for r in only_old[:20])
        pytest.fail("\n".join(lines))
