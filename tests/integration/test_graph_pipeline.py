"""Integrationstests für den minimalen Prüf-Graph (Phase 2a).

Testet den vollständigen Graphdurchlauf mit mock-Abhängigkeiten,
ohne echte Dateien oder das Legacy-System zu benötigen.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from fibu.graph.runner import run_pruefung
from fibu.skills_runtime import SkillResult


def test_pipeline_durchlauf_ok(make_context: Any, tmp_path: Path) -> None:
    """Graph läuft mit mock-Kontext vollständig durch und schreibt Bericht."""
    ctx = make_context()
    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[SkillResult(skill_id="mock")]),
    ):
        result = run_pruefung(tmp_path)

    assert result["gesamtstatus"] == "ok"
    assert Path(result["bericht_md_pfad"]).exists()
    assert Path(result["bericht_html_pfad"]).exists()


def test_pipeline_durchlauf_mit_fehler_finding(make_context: Any, tmp_path: Path) -> None:
    """Gesamtstatus 'fehler' wenn ein Skill ein fehler-Finding liefert."""
    from fibu.contracts import Finding

    ctx = make_context()
    f = Finding(rule="test", severity="fehler", title="Testfehler", detail="Detail")
    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[SkillResult(skill_id="x", findings=[f])]),
    ):
        result = run_pruefung(tmp_path)

    assert result["gesamtstatus"] == "fehler"


def test_pipeline_kein_pdf_wirft_fehler(tmp_path: Path) -> None:
    """FileNotFoundError in load_context wird als FileNotFoundError weitergegeben."""
    with (
        patch("fibu.graph.nodes.load_context", side_effect=FileNotFoundError("kein PDF")),
        pytest.raises(FileNotFoundError, match="kein PDF"),
    ):
        run_pruefung(tmp_path)


def test_pipeline_bericht_enthaelt_skills_info(make_context: Any, tmp_path: Path) -> None:
    """Der erzeugte Bericht nennt den Prüfzeitraum."""
    ctx = make_context(year=2024, month=8)
    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[]),
    ):
        result = run_pruefung(tmp_path)

    md = Path(result["bericht_md_pfad"]).read_text(encoding="utf-8")
    assert "August" in md
    assert "2024" in md
