from __future__ import annotations

from pathlib import Path

from langgraph.graph.state import CompiledStateGraph

from .graph import create_graph
from .state import PruefState


def run_pruefung(
    ordner: Path,
    config: dict[str, object] | None = None,
    skills_dir: Path | None = None,
    *,
    _graph: CompiledStateGraph | None = None,  # type: ignore[type-arg]
) -> PruefState:
    """Führt einen vollständigen Prüflauf für den Periodenordner durch.

    Gibt den finalen Graph-State zurück. Wirft FileNotFoundError wenn kein BWA-PDF
    im Periodenordner gefunden wird.
    """
    graph = _graph or create_graph()
    initial: PruefState = {
        "ordner": str(ordner.expanduser().resolve()),
        "skills_dir": str((skills_dir or Path("skills")).resolve()),
        "config": config or {},
    }
    result: PruefState = graph.invoke(initial)  # type: ignore[assignment]
    if result.get("fehler"):
        raise FileNotFoundError(result["fehler"])
    return result
