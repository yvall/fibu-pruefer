"""Integrationstests für den Versand-Knoten (Schritt 2c)."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import MemorySaver

from fibu.contracts import Entscheidung
from fibu.graph.runner import freigeben_lauf, run_pruefung
from fibu.ingest.mail import NullMailSender
from fibu.skills_runtime import SkillResult
from fibu.store import LaufStore


def _store() -> LaufStore:
    return LaufStore(Path(":memory:"))


# ---------------------------------------------------------------------------
# Vollständiger Graph: interrupt → freigeben → versand_ok=True
# ---------------------------------------------------------------------------

def test_versand_nach_freigabe(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    ctx = make_context()
    cp = MemorySaver()
    sender = NullMailSender()

    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[SkillResult(skill_id="mock")]),
    ):
        run_result = run_pruefung(
            tmp_path, store=store, mit_mail=True, _checkpointer=cp
        )

    assert "__interrupt__" in run_result
    lauf_id = run_result["lauf_id"]

    entscheidung = Entscheidung(freigabe="freigegeben")
    result = freigeben_lauf(
        lauf_id, entscheidung, store, _checkpointer=cp, _mail_sender=sender
    )

    assert result.get("versand_ok") is True
    assert store.ist_versand_ok(lauf_id) is True

    lauf = store.alle_laeufe(str(tmp_path.resolve()))[0]
    assert lauf.status == "abgeschlossen"


# ---------------------------------------------------------------------------
# Idempotenz: zweites freigeben → versand_ok=True, kein zweiter Send
# ---------------------------------------------------------------------------

def test_versand_idempotent_bei_zweitem_freigeben(
    make_context: Any, tmp_path: Path
) -> None:
    store = _store()
    ctx = make_context()
    cp = MemorySaver()
    mock_sender = MagicMock(spec=NullMailSender)

    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[SkillResult(skill_id="mock")]),
    ):
        run_result = run_pruefung(
            tmp_path, store=store, mit_mail=True, _checkpointer=cp
        )

    lauf_id = run_result["lauf_id"]
    entscheidung = Entscheidung(freigabe="freigegeben")

    freigeben_lauf(lauf_id, entscheidung, store, _checkpointer=cp, _mail_sender=mock_sender)
    freigeben_lauf(lauf_id, entscheidung, store, _checkpointer=cp, _mail_sender=mock_sender)

    assert mock_sender.sende_bericht.call_count == 1


# ---------------------------------------------------------------------------
# Gesperrt → versand_ok=False, Status "gesperrt"
# ---------------------------------------------------------------------------

def test_versand_bei_gesperrter_freigabe(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    ctx = make_context()
    cp = MemorySaver()
    mock_sender = MagicMock(spec=NullMailSender)

    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[SkillResult(skill_id="mock")]),
    ):
        run_result = run_pruefung(
            tmp_path, store=store, mit_mail=True, _checkpointer=cp
        )

    lauf_id = run_result["lauf_id"]
    entscheidung = Entscheidung(freigabe="gesperrt")
    result = freigeben_lauf(
        lauf_id, entscheidung, store, _checkpointer=cp, _mail_sender=mock_sender
    )

    assert result.get("versand_ok") is False
    mock_sender.sende_bericht.assert_not_called()

    lauf = store.alle_laeufe(str(tmp_path.resolve()))[0]
    assert lauf.status == "gesperrt"


# ---------------------------------------------------------------------------
# Trockenlauf: trocken=True → NullMailSender, kein SMTP-Aufruf
# ---------------------------------------------------------------------------

def test_trocken_verwendet_null_sender(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    ctx = make_context()
    cp = MemorySaver()

    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[SkillResult(skill_id="mock")]),
    ):
        run_result = run_pruefung(
            tmp_path, store=store, mit_mail=True, _checkpointer=cp
        )

    lauf_id = run_result["lauf_id"]
    entscheidung = Entscheidung(freigabe="freigegeben")

    # trocken=True ohne _mail_sender → sollte NullMailSender nutzen, kein SmtpMailSender
    with patch("fibu.ingest.mail.SmtpMailSender") as smtp_cls:
        result = freigeben_lauf(
            lauf_id, entscheidung, store, trocken=True, _checkpointer=cp
        )

    smtp_cls.aus_config.assert_not_called()
    assert result.get("versand_ok") is True
