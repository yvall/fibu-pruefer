from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from fibu.store import LaufStore

from .nodes import (
    bewerte,
    erstelle_bericht,
    fuehre_skills_aus,
    lade_kontext,
    versand,
    warte_auf_freigabe,
)
from .state import PruefState

if TYPE_CHECKING:
    from fibu.ingest.mail import MailSender
    from fibu.llm import LlmClient

# Typen, die der SqliteSaver über msgpack deserialisieren darf
MSGPACK_ALLOWLIST: list[tuple[str, ...]] = [
    ("fibu.skills_runtime.runner", "SkillResult"),
    ("fibu.contracts.finding", "Finding"),
    ("fibu.contracts.finding", "Calc"),
    ("fibu.contracts.finding", "Ref"),
]


def _weiter_nach_laden(state: PruefState) -> str:
    return "fehler" if state.get("fehler") else "weiter"


def create_graph(
    store: LaufStore,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    mail_sender: MailSender | None = None,
    llm: LlmClient | None = None,
    experimentelle_aktiv: bool = False,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Baut und kompiliert den Prüf-Graph.

    Knoten-Funktionen werden als Closures erzeugt, die store, mail_sender und llm einfangen.
    checkpointer ist für interrupt()/resume erforderlich; ohne ihn kein Interrupt.
    mail_sender: NullMailSender wenn None (Trockenlauf oder kein --mail).
    llm: NullLlmClient wenn None (LLM-Skills geben info-Finding zurück).
    experimentelle_aktiv: Skills mit status=experimental nur ausführen wenn True.
    """
    from fibu.ingest.mail import NullMailSender

    sender: MailSender = mail_sender or NullMailSender()

    g: StateGraph[PruefState] = StateGraph(PruefState)

    g.add_node("lade_kontext",        lambda s: lade_kontext(s, store))
    g.add_node("fuehre_skills_aus",   lambda s: fuehre_skills_aus(s, store, llm, experimentelle_aktiv))
    g.add_node("bewerte",             lambda s: bewerte(s, store))
    g.add_node("erstelle_bericht",    lambda s: erstelle_bericht(s, store))
    g.add_node("warte_auf_freigabe",  lambda s: warte_auf_freigabe(s, store))
    g.add_node("versand",             lambda s: versand(s, store, sender))

    g.add_edge(START, "lade_kontext")
    g.add_conditional_edges(
        "lade_kontext",
        _weiter_nach_laden,
        {"fehler": END, "weiter": "fuehre_skills_aus"},
    )
    g.add_edge("fuehre_skills_aus", "bewerte")
    g.add_edge("bewerte", "erstelle_bericht")
    g.add_edge("erstelle_bericht", "warte_auf_freigabe")
    g.add_edge("warte_auf_freigabe", "versand")
    g.add_edge("versand", END)

    return g.compile(checkpointer=checkpointer)
