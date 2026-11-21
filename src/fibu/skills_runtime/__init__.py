from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

from fibu.contracts import Context

from .loader import SkillManifest, load_manifests
from .runner import SkillResult, run_one_skill
from .scheduler import topological_waves

if TYPE_CHECKING:
    from fibu.llm import LlmClient

__all__ = [
    "SkillManifest",
    "SkillResult",
    "load_manifests",
    "run_skills",
    "topological_waves",
]


def run_skills(
    ctx: Context,
    skills_dir: Path,
    llm: LlmClient | None = None,
    experimentelle_aktiv: bool = False,
) -> list[SkillResult]:
    """Lädt alle Skills, sortiert nach Abhängigkeiten und führt sie wellenweise parallel aus.

    Ein fehlerhafter Skill erzeugt ein Finding „Prüfung nicht durchgeführt" und
    bricht den Gesamtlauf nicht ab.
    llm: LlmClient-Instanz für LLM-Skills; None → NullLlmClient (kein LLM-Aufruf).
    experimentelle_aktiv: Skills mit status=experimental werden nur ausgeführt, wenn True.

    Skills mit „context.befunde" in inputs laufen zwingend nach allen anderen Skills.
    ctx.befunde wird unmittelbar vor diesen Skills aus den gesammelten Findings befüllt.
    """
    manifests = load_manifests(skills_dir)
    if not manifests:
        return []

    # Skills die ctx.befunde benötigen, laufen nach allen normalen Skills
    befunde_skills = [m for m in manifests if "context.befunde" in m.inputs]
    normale_skills = [m for m in manifests if "context.befunde" not in m.inputs]

    normale_waves = topological_waves(normale_skills)
    befunde_waves = topological_waves(befunde_skills)

    results: list[SkillResult] = []
    with ThreadPoolExecutor() as pool:
        for wave in normale_waves:
            futures = {
                pool.submit(run_one_skill, m, ctx, llm, experimentelle_aktiv): m
                for m in wave
            }
            for future in futures:
                result = future.result()
                results.append(result)
                # vormonat-fortschreibung schreibt changed_accounts für klaerungsliste
                if "changed" in result.meta:
                    ctx.changed_accounts = result.meta["changed"]

        if befunde_waves:
            ctx.befunde = [f for r in results for f in r.findings]
            for wave in befunde_waves:
                futures = {
                    pool.submit(run_one_skill, m, ctx, llm, experimentelle_aktiv): m
                    for m in wave
                }
                for future in futures:
                    result = future.result()
                    results.append(result)
                    if "changed" in result.meta:
                        ctx.changed_accounts = result.meta["changed"]

    return results
