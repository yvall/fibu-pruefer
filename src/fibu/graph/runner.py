from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from fibu.contracts import Entscheidung
from fibu.store import LaufStore

from .graph import MSGPACK_ALLOWLIST, create_graph
from .state import PruefState


def _invoke(
    initial: PruefState,
    store: LaufStore,
    checkpointer: Any,
    thread_id: str,
) -> PruefState:
    graph = create_graph(store, checkpointer)
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
    *,
    _checkpointer: Any = None,
) -> PruefState:
    """Startet einen neuen Prüflauf für den Periodenordner.

    Gibt den finalen State zurück. Bei __interrupt__ im State ist der Lauf
    pausiert (mit_mail=True); der Aufrufer soll dann `freigeben_lauf()` nutzen.
    Wirft FileNotFoundError wenn kein BWA-PDF vorhanden.
    """
    from fibu.config import LokaleConfig

    cfg = LokaleConfig.laden()
    store = store or LaufStore(cfg.store.sqlite_pfad)

    lauf_id = str(uuid.uuid4())
    store.erstelle_lauf(lauf_id, str(ordner.expanduser().resolve()))

    initial: PruefState = {
        "ordner": str(ordner.expanduser().resolve()),
        "skills_dir": str((skills_dir or Path("skills")).resolve()),
        "config": config or {},
        "lauf_id": lauf_id,
        "mit_mail": mit_mail,
    }

    if _checkpointer is not None:
        result = _invoke(initial, store, _checkpointer, lauf_id)
    elif mit_mail:
        db_pfad = str(cfg.store.sqlite_pfad)
        from langgraph.checkpoint.sqlite import SqliteSaver
        with SqliteSaver.from_conn_string(db_pfad) as saver:
            cp = saver.with_allowlist(MSGPACK_ALLOWLIST)
            result = _invoke(initial, store, cp, lauf_id)
    else:
        result = _invoke(initial, store, MemorySaver(), lauf_id)

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
    *,
    _checkpointer: Any = None,
) -> PruefState:
    """Setzt einen pausierten Lauf fort.

    Ruft graph.invoke(Command(resume=…)) mit der Lauf-ID als thread_id auf.
    """
    from langgraph.types import Command

    from fibu.config import LokaleConfig

    if _checkpointer is not None:
        graph = create_graph(store, _checkpointer)
        result: PruefState = graph.invoke(  # type: ignore[assignment]
            Command(resume=entscheidung.model_dump()),
            config={"configurable": {"thread_id": lauf_id}},
        )
    else:
        db_pfad = str(LokaleConfig.laden().store.sqlite_pfad)
        from langgraph.checkpoint.sqlite import SqliteSaver
        with SqliteSaver.from_conn_string(db_pfad) as saver:
            cp = saver.with_allowlist(MSGPACK_ALLOWLIST)
            graph = create_graph(store, cp)
            result = graph.invoke(  # type: ignore[assignment]
                Command(resume=entscheidung.model_dump()),
                config={"configurable": {"thread_id": lauf_id}},
            )

    store.aktualisiere_status(lauf_id, "abgeschlossen")
    return result
