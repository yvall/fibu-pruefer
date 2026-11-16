from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from fibu.contracts import Finding
from fibu.graph.nodes import bewerte, erstelle_bericht, fuehre_skills_aus, lade_kontext
from fibu.graph.state import PruefState
from fibu.skills_runtime import SkillResult


def _basis(tmp_path: Path) -> PruefState:
    return {"ordner": str(tmp_path), "skills_dir": "skills", "config": {}}


def test_lade_kontext_setzt_kontext(make_context: Any, tmp_path: Path) -> None:
    ctx = make_context()
    with patch("fibu.graph.nodes.load_context", return_value=ctx):
        result = lade_kontext(_basis(tmp_path))
    assert result["kontext"] is ctx
    assert "fehler" not in result


def test_lade_kontext_setzt_fehler_bei_kein_pdf(tmp_path: Path) -> None:
    with patch("fibu.graph.nodes.load_context", side_effect=FileNotFoundError("kein PDF")):
        result = lade_kontext(_basis(tmp_path))
    assert result.get("fehler") == "kein PDF"
    assert "kontext" not in result


def test_fuehre_skills_aus_delegiert(make_context: Any, tmp_path: Path) -> None:
    ctx = make_context()
    r = SkillResult(skill_id="mock")
    state: PruefState = {**_basis(tmp_path), "kontext": ctx}
    with patch("fibu.graph.nodes.run_skills", return_value=[r]):
        result = fuehre_skills_aus(state)
    assert result["skill_results"] == [r]


def test_bewerte_ok(make_context: Any, tmp_path: Path) -> None:
    state: PruefState = {
        **_basis(tmp_path),
        "kontext": make_context(),
        "skill_results": [SkillResult(skill_id="x")],
    }
    assert bewerte(state)["gesamtstatus"] == "ok"


def test_bewerte_pruefen(make_context: Any, tmp_path: Path) -> None:
    f = Finding(rule="x", severity="pruefen", title="A", detail="B")
    state: PruefState = {
        **_basis(tmp_path),
        "kontext": make_context(),
        "skill_results": [SkillResult(skill_id="x", findings=[f])],
    }
    assert bewerte(state)["gesamtstatus"] == "pruefen"


def test_bewerte_fehler(make_context: Any, tmp_path: Path) -> None:
    f = Finding(rule="x", severity="fehler", title="A", detail="B")
    state: PruefState = {
        **_basis(tmp_path),
        "kontext": make_context(),
        "skill_results": [SkillResult(skill_id="x", findings=[f])],
    }
    assert bewerte(state)["gesamtstatus"] == "fehler"


def test_erstelle_bericht_schreibt_dateien(make_context: Any, tmp_path: Path) -> None:
    state: PruefState = {
        **_basis(tmp_path),
        "kontext": make_context(),
        "skill_results": [SkillResult(skill_id="mock")],
        "gesamtstatus": "ok",
    }
    result = erstelle_bericht(state)
    md = Path(str(result["bericht_md_pfad"]))
    html = Path(str(result["bericht_html_pfad"]))
    assert md.exists()
    assert html.exists()
    assert "Prüfbericht" in md.read_text(encoding="utf-8")


def test_erstelle_bericht_enthaelt_monat(make_context: Any, tmp_path: Path) -> None:
    state: PruefState = {
        **_basis(tmp_path),
        "kontext": make_context(month=3, year=2025),
        "skill_results": [],
        "gesamtstatus": "ok",
    }
    result = erstelle_bericht(state)
    md = Path(str(result["bericht_md_pfad"]))
    inhalt = md.read_text(encoding="utf-8")
    assert "März" in inhalt
    assert "2025" in inhalt
