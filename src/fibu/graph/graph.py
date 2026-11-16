from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .nodes import bewerte, erstelle_bericht, fuehre_skills_aus, lade_kontext
from .state import PruefState


def _weiter_nach_laden(state: PruefState) -> str:
    return "fehler" if state.get("fehler") else "weiter"


def create_graph() -> CompiledStateGraph:  # type: ignore[type-arg]
    g: StateGraph[PruefState] = StateGraph(PruefState)

    g.add_node("lade_kontext", lade_kontext)
    g.add_node("fuehre_skills_aus", fuehre_skills_aus)
    g.add_node("bewerte", bewerte)
    g.add_node("erstelle_bericht", erstelle_bericht)

    g.add_edge(START, "lade_kontext")
    g.add_conditional_edges(
        "lade_kontext",
        _weiter_nach_laden,
        {"fehler": END, "weiter": "fuehre_skills_aus"},
    )
    g.add_edge("fuehre_skills_aus", "bewerte")
    g.add_edge("bewerte", "erstelle_bericht")
    g.add_edge("erstelle_bericht", END)

    return g.compile()
