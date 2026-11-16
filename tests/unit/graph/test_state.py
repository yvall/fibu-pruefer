from __future__ import annotations

from typing import Any

from fibu.graph.state import PruefState


def test_pflichtfelder_setzbar() -> None:
    s: PruefState = {
        "ordner": "/tmp", "skills_dir": "skills", "config": {},
        "lauf_id": "abc-123", "mit_mail": False,
    }
    assert s["lauf_id"] == "abc-123"
    assert s["mit_mail"] is False


def test_optionale_felder_fehlen_standardmaessig() -> None:
    s: PruefState = {
        "ordner": "/tmp", "skills_dir": "skills", "config": {},
        "lauf_id": "abc", "mit_mail": False,
    }
    assert "skill_results" not in s
    assert "kontext" not in s   # E3: kein kontext im State
    assert "fehler" not in s
    assert "entscheidung" not in s


def test_config_nimmt_werte_auf() -> None:
    s: PruefState = {
        "ordner": "/tmp", "skills_dir": "skills",
        "config": {"toleranz": 0.02},
        "lauf_id": "x", "mit_mail": False,
    }
    assert s["config"]["toleranz"] == 0.02


def test_alle_optionalen_felder_setzbar(make_context: Any) -> None:
    from fibu.contracts import Entscheidung
    from fibu.skills_runtime import SkillResult

    s: PruefState = {
        "ordner": "/tmp", "skills_dir": "skills", "config": {},
        "lauf_id": "x", "mit_mail": True,
        "skill_results": [SkillResult(skill_id="x")],
        "gesamtstatus": "ok",
        "bericht_md_pfad": "/tmp/b.md",
        "bericht_html_pfad": "/tmp/b.html",
        "entscheidung": Entscheidung(freigabe="freigegeben"),
        "fehler": "test",
    }
    assert s["gesamtstatus"] == "ok"
    assert s["entscheidung"].freigabe == "freigegeben"
