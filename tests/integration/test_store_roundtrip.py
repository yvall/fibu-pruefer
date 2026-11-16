"""Roundtrip-Test mit echter Auswertung (benötigt FIBU_GOLDEN_DIR).

Speichert den geladenen Kontext im LaufStore, lädt ihn zurück und prüft,
dass die Skills dieselben Befunde liefern wie auf dem Original-Kontext.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from fibu.skills_runtime import run_skills
from fibu.store import LaufStore


@pytest.fixture(scope="module")
def golden_dir() -> Path:
    d = os.environ.get("FIBU_GOLDEN_DIR")
    if not d:
        pytest.skip("FIBU_GOLDEN_DIR nicht gesetzt – Roundtrip-Test übersprungen")
    return Path(d)


def test_kontext_roundtrip_gleiche_befunde(golden_dir: Path) -> None:
    """Findings auf original vs. store-roundtrip Kontext müssen identisch sein."""
    from fibu.ingest import load_context

    ctx_original = load_context(golden_dir)

    store = LaufStore(Path(":memory:"))
    store.erstelle_lauf("roundtrip", str(golden_dir))
    store.speichere_kontext("roundtrip", ctx_original)
    ctx_geladen = store.lade_kontext("roundtrip")

    results_original = run_skills(ctx_original, skills_dir=Path("skills"))
    results_geladen = run_skills(ctx_geladen, skills_dir=Path("skills"))

    def _befunde(results):  # type: ignore[no-untyped-def]
        rows = [
            {"severity": f.severity, "title": f.title, "detail": f.detail}
            for r in results for f in r.findings if f.title
        ]
        return sorted(rows, key=lambda x: (x["severity"], x["title"]))

    assert _befunde(results_original) == _befunde(results_geladen), (
        "Befunde nach Kontext-Roundtrip weichen ab"
    )
