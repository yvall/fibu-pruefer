from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fibu.contracts import Context

from .loader import SkillManifest, load_manifests
from .runner import SkillResult, run_one_skill
from .scheduler import topological_waves

__all__ = [
    "SkillManifest",
    "SkillResult",
    "load_manifests",
    "run_skills",
    "topological_waves",
]


def run_skills(ctx: Context, skills_dir: Path) -> list[SkillResult]:
    """Lädt alle Skills, sortiert nach Abhängigkeiten und führt sie wellenweise parallel aus.

    Ein fehlerhafter Skill erzeugt ein Finding „Prüfung nicht durchgeführt" und
    bricht den Gesamtlauf nicht ab.
    """
    manifests = load_manifests(skills_dir)
    if not manifests:
        return []
    waves = topological_waves(manifests)
    results: list[SkillResult] = []
    with ThreadPoolExecutor() as pool:
        for wave in waves:
            futures = {pool.submit(run_one_skill, m, ctx): m for m in wave}
            for future in futures:
                results.append(future.result())
    return results
