"""Regressionstests: experimentell/deaktiviert-Flags überleben den Graphdurchlauf.

Hintergrund: _dedupliziere_finding_ids in bewerte() baut SkillResult-Objekte neu
auf. Fehlte die explizite Übergabe von experimentell= und deaktiviert=, wurden
die Flags auf den Dataclass-Default False zurückgesetzt. Der KI-gestützt-Abschnitt
im Bericht blieb dann leer oder fehlte ganz.

Bekannte weitere Stellen, die experimentell noch nicht setzen (Fehlerpfade; ohne
eigenen Fix-Commit, da sie den Hauptflow nicht betreffen):
  - runner.py E7-Fallback (braucht_llm + NullLlmClient, aber experimentelle_aktiv=True)
  - runner.py check.py-not-found und Exception-Handler
  - sqlite.py _result_from_dict (DB-Roundtrip)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver

from fibu.contracts import Finding
from fibu.graph.nodes import _dedupliziere_finding_ids
from fibu.graph.runner import run_pruefung
from fibu.skills_runtime import SkillResult
from fibu.store import LaufStore


def _store() -> LaufStore:
    return LaufStore(Path(":memory:"))


def _basis(tmp_path: Path, lauf_id: str = "test-lauf") -> dict[str, object]:
    return {
        "ordner": str(tmp_path), "skills_dir": "skills", "config": {},
        "lauf_id": lauf_id, "mit_mail": False,
    }


# ---------------------------------------------------------------------------
# Direkter Unittest: _dedupliziere_finding_ids bewahrt Flags
# ---------------------------------------------------------------------------

def test_dedupliziere_bewahrt_experimentell_flag() -> None:
    """Flags überleben _dedupliziere_finding_ids – scheitert ohne den Fix."""
    r = SkillResult(skill_id="exp", findings=[], experimentell=True, deaktiviert=False)
    out, _ = _dedupliziere_finding_ids([r])
    assert out[0].experimentell is True


def test_dedupliziere_bewahrt_deaktiviert_flag() -> None:
    """deaktiviert=True überlebt _dedupliziere_finding_ids – scheitert ohne Fix."""
    r = SkillResult(skill_id="exp", findings=[], experimentell=True, deaktiviert=True)
    out, _ = _dedupliziere_finding_ids([r])
    assert out[0].deaktiviert is True


def test_dedupliziere_normaler_skill_flags_bleiben_false() -> None:
    f = Finding(rule="x", severity="info", title="OK", detail="")
    r = SkillResult(skill_id="x", findings=[f], experimentell=False, deaktiviert=False)
    out, _ = _dedupliziere_finding_ids([r])
    assert out[0].experimentell is False
    assert out[0].deaktiviert is False


def test_dedupliziere_bewahrt_flags_auch_mit_findings() -> None:
    """Flag-Erhalt auch wenn Findings vorhanden sind (und dedupliziert werden)."""
    f = Finding(rule="exp", severity="info", title="Extrahiert", detail="Brutto: 50,00")
    r = SkillResult(skill_id="exp", findings=[f], experimentell=True, deaktiviert=False)
    out, _ = _dedupliziere_finding_ids([r])
    assert out[0].experimentell is True
    assert len(out[0].findings) == 1


# ---------------------------------------------------------------------------
# Voller Graphdurchlauf: Bericht enthält KI-gestützt-Abschnitt
# Beide Tests scheitern ohne den nodes.py-Fix, weil bewerte() die Flags verliert.
# ---------------------------------------------------------------------------

def test_pipeline_deaktiviert_bericht_enthaelt_hinweis(
    make_context: Any, tmp_path: Path
) -> None:
    """Deaktivierter experimenteller Skill → Bericht enthält Deaktiviert-Hinweis."""
    store = _store()
    ctx = make_context()
    deakt = SkillResult(
        skill_id="beleg-extraktion",
        findings=[],
        experimentell=True,
        deaktiviert=True,
    )
    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[deakt]),
    ):
        result = run_pruefung(tmp_path, store=store, _checkpointer=MemorySaver())

    md = Path(result["bericht_md_pfad"]).read_text(encoding="utf-8")
    assert "KI-gestützt" in md
    assert "deaktiviert" in md
    assert "beleg-extraktion" in md


def test_pipeline_experimentell_aktiv_bericht_enthaelt_label(
    make_context: Any, tmp_path: Path
) -> None:
    """Aktiver experimenteller Skill → Bericht enthält *(experimentell)*-Label."""
    store = _store()
    ctx = make_context()
    finding = Finding(
        rule="beleg-extraktion", severity="info",
        title="Felder extrahiert", detail="Brutto: 120,00",
    )
    aktiv = SkillResult(
        skill_id="beleg-extraktion",
        findings=[finding],
        experimentell=True,
        deaktiviert=False,
    )
    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[aktiv]),
    ):
        result = run_pruefung(tmp_path, store=store, _checkpointer=MemorySaver())

    md = Path(result["bericht_md_pfad"]).read_text(encoding="utf-8")
    assert "KI-gestützt" in md
    assert "experimentell" in md
    assert "Felder extrahiert" in md
