"""Knoten-Funktionen für den Prüf-Graph.

Jede Funktion nimmt (state, store) und gibt ein partielles State-Dict zurück.
graph.py wickelt sie in Closures, die den store einfangen.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from langgraph.types import interrupt

from fibu.contracts import Entscheidung, Finding
from fibu.ingest import load_context
from fibu.report import overall_severity, to_html, to_markdown
from fibu.skills_runtime import SkillResult, run_skills
from fibu.store import LaufStore

from .state import PruefState

if TYPE_CHECKING:
    from fibu.ingest.mail import MailSender
    from fibu.llm import LlmClient

# ---------------------------------------------------------------------------
# Hilfsfunktion: ID-Kollisionen auflösen
# ---------------------------------------------------------------------------

def _dedupliziere_finding_ids(
    results: list[SkillResult],
) -> tuple[list[SkillResult], list[Finding]]:
    """Vergibt Suffixe (#2, #3 …) an doppelte Finding-IDs.

    Gibt (bereinigtes results, info-Findings über Kollisionen) zurück.
    Kollisionen sind unerwünscht, aber kein Laufabbruch.
    """
    zaehler: dict[str, int] = {}
    neue_results: list[SkillResult] = []
    kollisionen: list[tuple[str, str, str]] = []  # (basis_id, skill_id, title)

    for result in results:
        neue_findings: list[Finding] = []
        for f in result.findings:
            basis_id = f.id  # id_suffix ist noch ""
            zaehler[basis_id] = zaehler.get(basis_id, 0) + 1
            n = zaehler[basis_id]
            if n > 1:
                kollisionen.append((basis_id, result.skill_id, f.title))
                f = f.model_copy(update={"id_suffix": f"#{n}"})
            neue_findings.append(f)
        neue_results.append(
            SkillResult(
                skill_id=result.skill_id, findings=neue_findings,
                meta=result.meta, error=result.error,
                experimentell=result.experimentell,
                deaktiviert=result.deaktiviert,
            )
        )

    info_findings: list[Finding] = []
    if kollisionen:
        details = "; ".join(
            f"{bid[:8]}: {sid}/{title[:30]}" for bid, sid, title in kollisionen
        )
        info_findings.append(Finding(
            rule="_kollisionen",
            severity="info",
            title=f"Finding-IDs mehrfach vergeben ({len(kollisionen)}×)",
            detail=f"Folgende IDs wurden mit Suffix versehen: {details}",
        ))

    return neue_results, info_findings


# ---------------------------------------------------------------------------
# Knoten
# ---------------------------------------------------------------------------

def lade_kontext(state: PruefState, store: LaufStore) -> dict[str, object]:
    ordner = Path(state["ordner"])
    config = state["config"]
    try:
        ctx = load_context(ordner, config=config)
    except FileNotFoundError as exc:
        return {"fehler": str(exc)}
    store.speichere_kontext(state["lauf_id"], ctx)
    return {}


def fuehre_skills_aus(
    state: PruefState,
    store: LaufStore,
    llm: LlmClient | None = None,
    experimentelle_aktiv: bool = False,
) -> dict[str, object]:
    ctx = store.lade_kontext(state["lauf_id"])
    skills_dir = Path(state["skills_dir"])
    results: list[SkillResult] = run_skills(
        ctx, skills_dir=skills_dir, llm=llm,
        experimentelle_aktiv=experimentelle_aktiv,
    )
    return {"skill_results": results}


def bewerte(state: PruefState, store: LaufStore) -> dict[str, object]:
    results = state["skill_results"]

    dedup_results, kollisions_infos = _dedupliziere_finding_ids(results)
    if kollisions_infos:
        dedup_results = dedup_results + [
            SkillResult(skill_id="_kollisionen", findings=kollisions_infos)
        ]

    store.speichere_findings(state["lauf_id"], dedup_results)

    return {
        "skill_results": dedup_results,
        "gesamtstatus": overall_severity(dedup_results),
    }


def erstelle_bericht(state: PruefState, store: LaufStore) -> dict[str, object]:
    ctx = store.lade_kontext(state["lauf_id"])
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


def warte_auf_freigabe(state: PruefState, store: LaufStore) -> dict[str, object]:
    """Interrupt-Knoten: pausiert den Lauf wenn --mail gesetzt ist.

    Ohne --mail: No-op. Mit --mail: wartet auf Entscheidung via Command(resume=…).
    """
    if not state["mit_mail"]:
        return {}

    resumed: object = interrupt({
        "bericht_md_pfad": state.get("bericht_md_pfad", ""),
        "gesamtstatus": state.get("gesamtstatus", ""),
        "lauf_id": state["lauf_id"],
    })
    entscheidung = (
        Entscheidung.model_validate(resumed)
        if isinstance(resumed, dict)
        else resumed
    )
    return {"entscheidung": entscheidung}


def versand(
    state: PruefState,
    store: LaufStore,
    mail_sender: MailSender,
) -> dict[str, object]:
    """Sendet den Prüfbericht nach Freigabe – genau einmal (idempotent).

    Ohne Freigabe (gesperrt oder kein --mail): No-op.
    SMTP-Exceptions propagieren; versand_ok wird nur bei Erfolg gesetzt.
    """
    if store.ist_versand_ok(state["lauf_id"]):
        return {"versand_ok": True}

    entscheidung = state.get("entscheidung")
    if not entscheidung or entscheidung.freigabe != "freigegeben":
        return {"versand_ok": False}

    ctx = store.lade_kontext(state["lauf_id"])
    a = ctx.auswertung
    betreff = (
        f"Prüfbericht Buchhaltung {a.month:02d}/{a.year}: "
        f"{state.get('gesamtstatus', '').upper()}"
    )
    text = Path(state["bericht_md_pfad"]).read_text(encoding="utf-8")
    mail_sender.sende_bericht(
        betreff=betreff,
        text=text,
        md_pfad=Path(state["bericht_md_pfad"]),
        html_pfad=Path(state["bericht_html_pfad"]),
    )
    store.setze_versand_ok(state["lauf_id"])
    return {"versand_ok": True}
