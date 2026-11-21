from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from fibu.contracts import Entscheidung
from fibu.graph.nodes import versand
from fibu.graph.state import PruefState
from fibu.ingest.mail import NullMailSender
from fibu.store import LaufStore


def _store() -> LaufStore:
    return LaufStore(Path(":memory:"))


def _basis(
    tmp_path: Path,
    lauf_id: str = "lauf-1",
    mit_mail: bool = True,
    freigabe: str = "freigegeben",
) -> PruefState:
    bericht_md = tmp_path / "Pruefbericht_2024-01.md"
    bericht_html = tmp_path / "Pruefbericht_2024-01.html"
    bericht_md.write_text("# Bericht")
    bericht_html.write_bytes(b"<html/>")
    state: PruefState = {
        "ordner": str(tmp_path),
        "skills_dir": "skills",
        "config": {},
        "lauf_id": lauf_id,
        "mit_mail": mit_mail,
        "gesamtstatus": "ok",
        "bericht_md_pfad": str(bericht_md),
        "bericht_html_pfad": str(bericht_html),
        "entscheidung": Entscheidung(freigabe=freigabe),  # type: ignore[arg-type]
    }
    return state


def _store_mit_kontext(make_context: Any, lauf_id: str = "lauf-1") -> LaufStore:
    store = _store()
    store.erstelle_lauf(lauf_id, "/tmp")
    ctx = make_context()
    store.speichere_kontext(lauf_id, ctx)
    return store


# ---------------------------------------------------------------------------
# freigegeben → versand_ok=True
# ---------------------------------------------------------------------------

def test_versand_freigegeben_sendet_und_setzt_ok(
    make_context: Any, tmp_path: Path
) -> None:
    store = _store_mit_kontext(make_context)
    sender = NullMailSender()
    state = _basis(tmp_path, freigabe="freigegeben")

    result = versand(state, store, sender)

    assert result["versand_ok"] is True
    assert store.ist_versand_ok("lauf-1") is True


# ---------------------------------------------------------------------------
# gesperrt → versand_ok=False, kein Versand
# ---------------------------------------------------------------------------

def test_versand_gesperrt_kein_send(make_context: Any, tmp_path: Path) -> None:
    store = _store_mit_kontext(make_context)
    mock_sender = MagicMock(spec=NullMailSender)
    state = _basis(tmp_path, freigabe="gesperrt")

    result = versand(state, store, mock_sender)

    assert result["versand_ok"] is False
    mock_sender.sende_bericht.assert_not_called()
    assert store.ist_versand_ok("lauf-1") is False


# ---------------------------------------------------------------------------
# kein --mail (kein entscheidung) → versand_ok=False
# ---------------------------------------------------------------------------

def test_versand_ohne_entscheidung_kein_send(make_context: Any, tmp_path: Path) -> None:
    store = _store()
    store.erstelle_lauf("lauf-1", "/tmp")
    ctx = make_context()
    store.speichere_kontext("lauf-1", ctx)

    bericht_md = tmp_path / "b.md"
    bericht_md.write_text("x")
    bericht_html = tmp_path / "b.html"
    bericht_html.write_bytes(b"y")

    state: PruefState = {
        "ordner": str(tmp_path), "skills_dir": "skills", "config": {},
        "lauf_id": "lauf-1", "mit_mail": False,
        "gesamtstatus": "ok",
        "bericht_md_pfad": str(bericht_md),
        "bericht_html_pfad": str(bericht_html),
        # kein entscheidung-Feld
    }
    mock_sender = MagicMock(spec=NullMailSender)
    result = versand(state, store, mock_sender)

    assert result["versand_ok"] is False
    mock_sender.sende_bericht.assert_not_called()


# ---------------------------------------------------------------------------
# Idempotenz: zweiter Aufruf → True, kein zweiter Send
# ---------------------------------------------------------------------------

def test_versand_idempotent(make_context: Any, tmp_path: Path) -> None:
    store = _store_mit_kontext(make_context)
    mock_sender = MagicMock(spec=NullMailSender)
    state = _basis(tmp_path, freigabe="freigegeben")

    versand(state, store, mock_sender)      # erster Aufruf
    result = versand(state, store, mock_sender)  # zweiter Aufruf

    assert result["versand_ok"] is True
    assert mock_sender.sende_bericht.call_count == 1  # nur einmal gesendet
