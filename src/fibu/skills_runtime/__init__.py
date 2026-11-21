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
    """
    manifests = load_manifests(skills_dir)
    if not manifests:
        return []
    waves = topological_waves(manifests)
    results: list[SkillResult] = []
    with ThreadPoolExecutor() as pool:
        for wave in waves:
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
    return results
