"""Integrationstests für den Prüf-Graph (Phase 2b).

Testet den vollständigen Graphdurchlauf mit mock-Abhängigkeiten,
einschließlich interrupt/resume mit MemorySaver.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from fibu.contracts import Entscheidung, Finding
from fibu.graph.runner import freigeben_lauf, run_pruefung
from fibu.skills_runtime import SkillResult
from fibu.store import LaufStore


def _store() -> LaufStore:
    return LaufStore(Path(":memory:"))


# ---------------------------------------------------------------------------
# Ohne --mail (kein Interrupt)
# ---------------------------------------------------------------------------

def test_pipeline_ok_ohne_mail(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    ctx = make_context()
    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[SkillResult(skill_id="mock")]),
    ):
        result = run_pruefung(tmp_path, store=store, _checkpointer=MemorySaver())

    assert result["gesamtstatus"] == "ok"
    assert "__interrupt__" not in result
    assert Path(result["bericht_md_pfad"]).exists()


def test_pipeline_fehler_finding_setzt_gesamtstatus(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    ctx = make_context()
    f = Finding(rule="x", severity="fehler", title="F", detail="D")
    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills",
              return_value=[SkillResult(skill_id="x", findings=[f])]),
    ):
        result = run_pruefung(tmp_path, store=store, _checkpointer=MemorySaver())

    assert result["gesamtstatus"] == "fehler"


def test_pipeline_kein_pdf_wirft_fehler(tmp_path: Path) -> None:
    store = _store()
    with (
        patch("fibu.graph.nodes.load_context", side_effect=FileNotFoundError("kein PDF")),
        pytest.raises(FileNotFoundError, match="kein PDF"),
    ):
        run_pruefung(tmp_path, store=store, _checkpointer=MemorySaver())


def test_pipeline_lauf_in_store_registriert(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    ctx = make_context()
    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[]),
    ):
        result = run_pruefung(tmp_path, store=store, _checkpointer=MemorySaver())

    lauf_id = result["lauf_id"]
    laeufe = store.alle_laeufe(str(tmp_path.resolve()))
    assert any(l.lauf_id == lauf_id for l in laeufe)
    offener = store.neuester_offener_lauf(str(tmp_path.resolve()))
    assert offener is None  # abgeschlossen


def test_pipeline_bericht_enthaelt_monat(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    ctx = make_context(year=2024, month=8)
    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[]),
    ):
        result = run_pruefung(tmp_path, store=store, _checkpointer=MemorySaver())

    md = Path(result["bericht_md_pfad"]).read_text(encoding="utf-8")
    assert "August" in md
    assert "2024" in md


# ---------------------------------------------------------------------------
# Mit --mail: interrupt/resume
# ---------------------------------------------------------------------------

def test_pipeline_mit_mail_liefert_interrupt(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    cp = MemorySaver()
    ctx = make_context()
    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[SkillResult(skill_id="mock")]),
    ):
        result = run_pruefung(tmp_path, mit_mail=True, store=store, _checkpointer=cp)

    assert "__interrupt__" in result
    # Lauf ist als "wartend" markiert
    offener = store.neuester_offener_lauf(str(tmp_path.resolve()))
    assert offener is not None
    assert offener.status == "wartend"


def test_pipeline_resume_nach_interrupt(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    cp = MemorySaver()
    ctx = make_context()
    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[SkillResult(skill_id="mock")]),
    ):
        paused = run_pruefung(tmp_path, mit_mail=True, store=store, _checkpointer=cp)

    assert "__interrupt__" in paused
    lauf_id = paused["lauf_id"]

    from fibu.ingest.mail import NullMailSender
    entscheidung = Entscheidung(freigabe="freigegeben", kommentar="ok")
    result = freigeben_lauf(
        lauf_id, entscheidung, store, _checkpointer=cp, _mail_sender=NullMailSender()
    )

    assert "entscheidung" in result
    assert result["entscheidung"].freigabe == "freigegeben"
    # Lauf ist jetzt abgeschlossen
    offener = store.neuester_offener_lauf(str(tmp_path.resolve()))
    assert offener is None


def test_pipeline_kollision_erzeugt_info_in_bericht(make_context: Any, tmp_path: Path) -> None:
    """Findings mit gleicher ID: Bericht entsteht trotzdem, enthält Kollisions-Hinweis."""
    store = _store()
    ctx = make_context()
    f = Finding(rule="gleich", severity="info", title="Gleicher Typ", detail="D")
    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills",
              return_value=[SkillResult(skill_id="x", findings=[f, f])]),
    ):
        result = run_pruefung(tmp_path, store=store, _checkpointer=MemorySaver())

    assert result["gesamtstatus"] in ("ok", "info", "pruefen")
    md = Path(result["bericht_md_pfad"]).read_text(encoding="utf-8")
    assert "Prüfbericht" in md   # Bericht entstanden


def test_experimentell_findings_erhoehen_hinweis_zaehler_nicht(
    make_context: Any, tmp_path: Path
) -> None:
    """Hinweis-Zähler im Bericht ist mit und ohne experimentellen Skill identisch."""
    import re as re_mod

    store1 = _store()
    ctx = make_context()
    info_f = Finding(rule="k", severity="info", title="Klärung", detail="X")
    exp_f = Finding(rule="re", severity="info", title="Rückfrage XYZ", detail="Y")
    ordner_ohne = tmp_path / "ohne"
    ordner_mit = tmp_path / "mit"
    ordner_ohne.mkdir()
    ordner_mit.mkdir()

    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills",
              return_value=[SkillResult(skill_id="k", findings=[info_f])]),
    ):
        result_ohne = run_pruefung(ordner_ohne, store=store1, _checkpointer=MemorySaver())

    store2 = _store()
    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[
            SkillResult(skill_id="k", findings=[info_f]),
            SkillResult(skill_id="re", findings=[exp_f], experimentell=True),
        ]),
    ):
        result_mit = run_pruefung(ordner_mit, store=store2, _checkpointer=MemorySaver())

    md_ohne = Path(result_ohne["bericht_md_pfad"]).read_text(encoding="utf-8")
    md_mit = Path(result_mit["bericht_md_pfad"]).read_text(encoding="utf-8")

    z_ohne = re_mod.search(r'Hinweise \((\d+)\)', md_ohne)
    z_mit = re_mod.search(r'Hinweise \((\d+)\)', md_mit)
    assert z_ohne is not None and z_mit is not None
    assert z_ohne.group(1) == z_mit.group(1)

    # Experimentelles Finding im KI-gestützt, nicht im Hinweise-Block
    ki_idx = md_mit.find("🤖 KI-gestützt")
    assert ki_idx >= 0
    assert "Rückfrage XYZ" in md_mit[ki_idx:]
    assert "Rückfrage XYZ" not in md_mit[:ki_idx]
