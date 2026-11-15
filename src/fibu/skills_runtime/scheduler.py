from __future__ import annotations

import warnings

from .loader import SkillManifest


def topological_waves(manifests: list[SkillManifest]) -> list[list[SkillManifest]]:
    """Gibt Wellen von Skills zurück, die innerhalb einer Welle parallel laufen können.

    Unbekannte Einträge in `runs_after` (kein passender Skill im Verzeichnis) werden
    ignoriert, damit optionale Abhängigkeiten keine Blockade erzeugen.
    Zirkuläre Abhängigkeiten werden mit einem RuntimeWarning behandelt.
    """
    known_ids = {m.skill_id for m in manifests}
    done: set[str] = set()
    remaining = list(manifests)
    waves: list[list[SkillManifest]] = []

    while remaining:
        wave = [
            m for m in remaining
            if all(dep in done or dep not in known_ids for dep in m.runs_after)
        ]
        if not wave:
            cycle_ids = [m.skill_id for m in remaining]
            warnings.warn(
                f"Zirkuläre oder unauflösbare Abhängigkeit in Skills: {cycle_ids}; "
                "alle verbleibenden Skills werden in einer Welle ausgeführt.",
                RuntimeWarning,
                stacklevel=2,
            )
            wave = list(remaining)

        wave_ids = {m.skill_id for m in wave}
        remaining = [m for m in remaining if m.skill_id not in wave_ids]
        done.update(wave_ids)
        waves.append(wave)

    return waves
