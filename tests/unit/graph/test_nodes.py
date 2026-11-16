from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from fibu.contracts import Finding
from fibu.graph.nodes import (
    bewerte,
    erstelle_bericht,
    fuehre_skills_aus,
    lade_kontext,
    warte_auf_freigabe,
)
from fibu.graph.state import PruefState
from fibu.skills_runtime import SkillResult
from fibu.store import LaufStore


def _store() -> LaufStore:
    return LaufStore(Path(":memory:"))


def _basis(tmp_path: Path, lauf_id: str = "test-lauf", mit_mail: bool = False) -> PruefState:
    return {
        "ordner": str(tmp_path), "skills_dir": "skills", "config": {},
        "lauf_id": lauf_id, "mit_mail": mit_mail,
    }


# ---------------------------------------------------------------------------
# lade_kontext
# ---------------------------------------------------------------------------

def test_lade_kontext_speichert_in_store(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    store.erstelle_lauf("test-lauf", str(tmp_path))
    ctx = make_context()
    with patch("fibu.graph.nodes.load_context", return_value=ctx):
        result = lade_kontext(_basis(tmp_path), store)
    # Kein kontext im Return-Dict (E3)
    assert "kontext" not in result
    assert "fehler" not in result
    # Aber im Store vorhanden
    assert store.lade_kontext("test-lauf") is not None


def test_lade_kontext_setzt_fehler_bei_kein_pdf(tmp_path: Path) -> None:
    store = _store()
    store.erstelle_lauf("test-lauf", str(tmp_path))
    with patch("fibu.graph.nodes.load_context", side_effect=FileNotFoundError("kein PDF")):
        result = lade_kontext(_basis(tmp_path), store)
    assert result.get("fehler") == "kein PDF"


# ---------------------------------------------------------------------------
# fuehre_skills_aus
# ---------------------------------------------------------------------------

def test_fuehre_skills_aus_laedt_kontext_aus_store(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    ctx = make_context()
    store.erstelle_lauf("test-lauf", str(tmp_path))
    store.speichere_kontext("test-lauf", ctx)
    r = SkillResult(skill_id="mock")
    with patch("fibu.graph.nodes.run_skills", return_value=[r]):
        result = fuehre_skills_aus(_basis(tmp_path), store)
    assert result["skill_results"] == [r]


# ---------------------------------------------------------------------------
# bewerte
# ---------------------------------------------------------------------------

def test_bewerte_ok(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    ctx = make_context()
    store.erstelle_lauf("test-lauf", str(tmp_path))
    store.speichere_kontext("test-lauf", ctx)
    state: PruefState = {**_basis(tmp_path), "skill_results": [SkillResult(skill_id="x")]}
    result = bewerte(state, store)
    assert result["gesamtstatus"] == "ok"
    assert "skill_results" in result  # bewerte gibt skill_results zurück (ggf. dedup)


def test_bewerte_kollision_erzeugt_info_finding(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    ctx = make_context()
    store.erstelle_lauf("test-lauf", str(tmp_path))
    store.speichere_kontext("test-lauf", ctx)
    f = Finding(rule="gleich", severity="info", title="Gleicher Titel", detail="D")
    state: PruefState = {
        **_basis(tmp_path),
        "skill_results": [SkillResult(skill_id="x", findings=[f, f])],
    }
    result = bewerte(state, store)
    all_findings = [f for r in result["skill_results"] for f in r.findings]  # type: ignore[union-attr]
    info_findings = [f for f in all_findings if f.rule == "_kollisionen"]
    assert len(info_findings) == 1


def test_bewerte_keine_kollision_kein_info(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    ctx = make_context()
    store.erstelle_lauf("test-lauf", str(tmp_path))
    store.speichere_kontext("test-lauf", ctx)
    f1 = Finding(rule="x", severity="info", title="Titel A", detail="D")
    f2 = Finding(rule="x", severity="info", title="Titel B", detail="D")
    state: PruefState = {
        **_basis(tmp_path),
        "skill_results": [SkillResult(skill_id="x", findings=[f1, f2])],
    }
    result = bewerte(state, store)
    all_findings = [f for r in result["skill_results"] for f in r.findings]  # type: ignore[union-attr]
    assert all(f.rule != "_kollisionen" for f in all_findings)


# ---------------------------------------------------------------------------
# erstelle_bericht
# ---------------------------------------------------------------------------

def test_erstelle_bericht_schreibt_dateien(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    ctx = make_context()
    store.erstelle_lauf("test-lauf", str(tmp_path))
    store.speichere_kontext("test-lauf", ctx)
    state: PruefState = {
        **_basis(tmp_path),
        "skill_results": [SkillResult(skill_id="mock")],
        "gesamtstatus": "ok",
    }
    result = erstelle_bericht(state, store)
    assert Path(str(result["bericht_md_pfad"])).exists()
    assert Path(str(result["bericht_html_pfad"])).exists()


# ---------------------------------------------------------------------------
# warte_auf_freigabe
# ---------------------------------------------------------------------------

def test_warte_auf_freigabe_ohne_mail_kein_interrupt(tmp_path: Path) -> None:
    store = _store()
    store.erstelle_lauf("test-lauf", str(tmp_path))
    state: PruefState = {**_basis(tmp_path, mit_mail=False), "gesamtstatus": "ok"}
    result = warte_auf_freigabe(state, store)
    assert result == {}


def test_warte_auf_freigabe_mit_mail_ruft_interrupt(tmp_path: Path) -> None:
    store = _store()
    store.erstelle_lauf("test-lauf", str(tmp_path))
    state: PruefState = {
        **_basis(tmp_path, mit_mail=True),
        "gesamtstatus": "ok",
        "bericht_md_pfad": "/tmp/b.md",
    }
    mock_interrupt = MagicMock(return_value={"freigabe": "freigegeben", "kommentar": ""})
    with patch("fibu.graph.nodes.interrupt", mock_interrupt):  # top-level import, direkt patchbar
        result = warte_auf_freigabe(state, store)
    mock_interrupt.assert_called_once()
    assert "entscheidung" in result
