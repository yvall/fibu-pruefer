"""Knoten-Funktionen für den Prüf-Graph."""
from __future__ import annotations

from pathlib import Path

from fibu.ingest import load_context
from fibu.report import overall_severity, to_html, to_markdown
from fibu.skills_runtime import SkillResult, run_skills

from .state import PruefState


def lade_kontext(state: PruefState) -> dict[str, object]:
    ordner = Path(state["ordner"])
    config = state["config"]
    try:
        ctx = load_context(ordner, config=config)
    except FileNotFoundError as exc:
        return {"fehler": str(exc)}
    return {"kontext": ctx}


def fuehre_skills_aus(state: PruefState) -> dict[str, object]:
    ctx = state["kontext"]
    skills_dir = Path(state["skills_dir"])
    results: list[SkillResult] = run_skills(ctx, skills_dir=skills_dir)
    return {"skill_results": results}


def bewerte(state: PruefState) -> dict[str, object]:
    return {"gesamtstatus": overall_severity(state["skill_results"])}


def erstelle_bericht(state: PruefState) -> dict[str, object]:
    ctx = state["kontext"]
    results = state["skill_results"]
    a = ctx.auswertung

    out_dir = Path(state["ordner"]) / "Pruefbericht"
    out_dir.mkdir(exist_ok=True)
    stem = f"Pruefbericht_{a.year}-{a.month:02d}"
    md_path = out_dir / f"{stem}.md"
    html_path = out_dir / f"{stem}.html"
    md_path.write_text(to_markdown(a, results), encoding="utf-8")
    html_path.write_text(to_html(a, results), encoding="utf-8")

    return {
        "bericht_md_pfad": str(md_path),
        "bericht_html_pfad": str(html_path),
    }
