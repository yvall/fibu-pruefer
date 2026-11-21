from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langgraph.checkpoint.memory import MemorySaver

from fibu.contracts import Entscheidung
from fibu.store import LaufStore

from .graph import MSGPACK_ALLOWLIST, create_graph
from .state import PruefState

if TYPE_CHECKING:
    from fibu.ingest.mail import MailSender
    from fibu.llm import LlmClient


def _invoke(
    initial: PruefState,
    store: LaufStore,
    checkpointer: Any,
    thread_id: str,
    mail_sender: MailSender | None = None,
    llm: LlmClient | None = None,
    experimentelle_aktiv: bool = False,
) -> PruefState:
    graph = create_graph(
        store, checkpointer,
        mail_sender=mail_sender, llm=llm,
        experimentelle_aktiv=experimentelle_aktiv,
    )
    result: PruefState = graph.invoke(  # type: ignore[assignment]
        initial,
        config={"configurable": {"thread_id": thread_id}},
    )
    return result


def run_pruefung(
    ordner: Path,
    config: dict[str, object] | None = None,
    skills_dir: Path | None = None,
    mit_mail: bool = False,
    store: LaufStore | None = None,
    llm: LlmClient | None = None,
    *,
    _checkpointer: Any = None,
) -> PruefState:
    """Startet einen neuen Prüflauf für den Periodenordner.

    Gibt den finalen State zurück. Bei __interrupt__ im State ist der Lauf
    pausiert (mit_mail=True); der Aufrufer soll dann `freigeben_lauf()` nutzen.
    Wirft FileNotFoundError wenn kein BWA-PDF vorhanden.
    llm: None → LLM-Client wird aus der Konfiguration geladen (OllamaClient oder NullLlmClient).
    """
    from fibu.config import LokaleConfig

    cfg = LokaleConfig.laden()
    store = store or LaufStore(cfg.store.sqlite_pfad)

    if llm is None:
        if cfg.llm.modell:
            from fibu.llm.ollama import OllamaClient
            llm = OllamaClient.aus_config(cfg.llm)
        else:
            from fibu.llm.null import NullLlmClient
            llm = NullLlmClient()

    experimentelle_aktiv = cfg.llm.experimentelle_skills_aktiv
    lauf_id = str(uuid.uuid4())
    store.erstelle_lauf(lauf_id, str(ordner.expanduser().resolve()))

    initial: PruefState = {
        "ordner": str(ordner.expanduser().resolve()),
        "skills_dir": str((skills_dir or Path("skills")).resolve()),
        "config": config or {},
        "lauf_id": lauf_id,
        "mit_mail": mit_mail,
    }

    from fibu.ingest.mail import NullMailSender
    null_sender = NullMailSender()

    if _checkpointer is not None:
        result = _invoke(initial, store, _checkpointer, lauf_id, null_sender, llm, experimentelle_aktiv)
    elif mit_mail:
        db_pfad = str(cfg.store.sqlite_pfad)
        from langgraph.checkpoint.sqlite import SqliteSaver
        with SqliteSaver.from_conn_string(db_pfad) as saver:
            cp = saver.with_allowlist(MSGPACK_ALLOWLIST)
            result = _invoke(initial, store, cp, lauf_id, null_sender, llm, experimentelle_aktiv)
    else:
        result = _invoke(initial, store, MemorySaver(), lauf_id, null_sender, llm, experimentelle_aktiv)

    # Lauf-Status nachführen
    if result.get("fehler"):
        store.aktualisiere_status(lauf_id, "fehler")
        raise FileNotFoundError(result["fehler"])
    if "__interrupt__" in result:
        store.aktualisiere_status(lauf_id, "wartend")
    else:
        store.aktualisiere_status(lauf_id, "abgeschlossen")

    return result


def freigeben_lauf(
    lauf_id: str,
    entscheidung: Entscheidung,
    store: LaufStore,
    trocken: bool = False,
    *,
    _checkpointer: Any = None,
    _mail_sender: MailSender | None = None,
) -> PruefState:
    """Setzt einen pausierten Lauf fort und versendet den Bericht nach Freigabe.

    trocken=True: NullMailSender (protokolliert, sendet nicht).
    _mail_sender: überschreibt den Sender (für Tests).
    """
    from langgraph.types import Command

    from fibu.config import LokaleConfig
    from fibu.ingest.mail import NullMailSender, SmtpMailSender

    if _mail_sender is not None:
        sender: MailSender = _mail_sender
    elif trocken:
        sender = NullMailSender()
    else:
        sender = SmtpMailSender.aus_config(LokaleConfig.laden().mail)

    if _checkpointer is not None:
        graph = create_graph(store, _checkpointer, mail_sender=sender)
        result: PruefState = graph.invoke(  # type: ignore[assignment]
            Command(resume=entscheidung.model_dump()),
            config={"configurable": {"thread_id": lauf_id}},
        )
    else:
        db_pfad = str(LokaleConfig.laden().store.sqlite_pfad)
        from langgraph.checkpoint.sqlite import SqliteSaver
        with SqliteSaver.from_conn_string(db_pfad) as saver:
            cp = saver.with_allowlist(MSGPACK_ALLOWLIST)
            graph = create_graph(store, cp, mail_sender=sender)
            result = graph.invoke(  # type: ignore[assignment]
                Command(resume=entscheidung.model_dump()),
                config={"configurable": {"thread_id": lauf_id}},
            )

    entscheidung_obj = result.get("entscheidung")
    if entscheidung_obj and entscheidung_obj.freigabe == "gesperrt":
        store.aktualisiere_status(lauf_id, "gesperrt")
    else:
        store.aktualisiere_status(lauf_id, "abgeschlossen")
    return result
