from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from fibu.store import LaufStore

from .nodes import (
    bewerte,
    erstelle_bericht,
    fuehre_skills_aus,
    lade_kontext,
    warte_auf_freigabe,
)
from .state import PruefState

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
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Baut und kompiliert den Prüf-Graph.

    Knoten-Funktionen werden als Closures erzeugt, die den store einfangen.
    checkpointer ist für interrupt()/resume erforderlich; ohne ihn kein Interrupt.
    """
    g: StateGraph[PruefState] = StateGraph(PruefState)

    g.add_node("lade_kontext",        lambda s: lade_kontext(s, store))
    g.add_node("fuehre_skills_aus",   lambda s: fuehre_skills_aus(s, store))
    g.add_node("bewerte",             lambda s: bewerte(s, store))
    g.add_node("erstelle_bericht",    lambda s: erstelle_bericht(s, store))
    g.add_node("warte_auf_freigabe",  lambda s: warte_auf_freigabe(s, store))

    g.add_edge(START, "lade_kontext")
    g.add_conditional_edges(
        "lade_kontext",
        _weiter_nach_laden,
        {"fehler": END, "weiter": "fuehre_skills_aus"},
    )
    g.add_edge("fuehre_skills_aus", "bewerte")
    g.add_edge("bewerte", "erstelle_bericht")
    g.add_edge("erstelle_bericht", "warte_auf_freigabe")
    g.add_edge("warte_auf_freigabe", END)

    return g.compile(checkpointer=checkpointer)
