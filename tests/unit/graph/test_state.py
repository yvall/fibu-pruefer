from __future__ import annotations

from typing import Any

from fibu.graph.state import PruefState


def test_pflichtfelder_setzbar() -> None:
    s: PruefState = {"ordner": "/tmp", "skills_dir": "skills", "config": {}}
    assert s["ordner"] == "/tmp"
    assert s["skills_dir"] == "skills"
    assert s["config"] == {}


def test_optionale_felder_fehlen_standardmaessig() -> None:
    s: PruefState = {"ordner": "/tmp", "skills_dir": "skills", "config": {}}
    assert "kontext" not in s
    assert "skill_results" not in s
    assert "gesamtstatus" not in s
    assert "fehler" not in s


def test_config_nimmt_werte_auf() -> None:
    s: PruefState = {
        "ordner": "/tmp",
        "skills_dir": "skills",
        "config": {"toleranz": 0.02, "monate_offen": 60},
    }
    assert s["config"]["toleranz"] == 0.02


def test_alle_felder_setzbar(make_context: Any) -> None:
    from fibu.skills_runtime import SkillResult

    s: PruefState = {
        "ordner": "/tmp",
        "skills_dir": "skills",
        "config": {},
        "kontext": make_context(),
        "skill_results": [SkillResult(skill_id="x")],
        "gesamtstatus": "ok",
        "bericht_md_pfad": "/tmp/bericht.md",
        "bericht_html_pfad": "/tmp/bericht.html",
        "fehler": "test-fehler",
    }
    assert s["gesamtstatus"] == "ok"
    assert s["fehler"] == "test-fehler"
