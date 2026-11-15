from __future__ import annotations

import importlib.abc
import importlib.util
import traceback
from dataclasses import dataclass, field
from typing import Any

from fibu.contracts import Context, Finding

from .loader import SkillManifest


@dataclass
class SkillResult:
    skill_id: str
    findings: list[Finding] = field(default_factory=list)
    # Optionale Metadaten, die der Skill an die Runtime zurückgeben kann
    # (z. B. changed_accounts nach vormonat-fortschreibung).
    meta: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def run_one_skill(manifest: SkillManifest, ctx: Context) -> SkillResult:
    """Führt einen einzelnen Skill aus. Fehler erzeugen ein Finding und brechen den Lauf nicht ab."""
    if not manifest.check_path.exists():
        return SkillResult(
            skill_id=manifest.skill_id,
            findings=[
                Finding(
                    rule=manifest.skill_id,
                    severity="fehler",
                    title="Prüfung nicht durchgeführt",
                    detail=f"check.py nicht gefunden: {manifest.check_path}",
                )
            ],
            error="check.py nicht gefunden",
        )
    try:
        spec = importlib.util.spec_from_file_location(
            f"_skills_runtime_{manifest.skill_id.replace('-', '_')}",
            manifest.check_path,
        )
        if spec is None:
            raise ImportError(f"Kann {manifest.check_path} nicht laden")
        loader = spec.loader
        if not isinstance(loader, importlib.abc.Loader):
            raise TypeError(f"Ungültiger Loader für {manifest.check_path}")
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        run_fn = mod.run
        findings: list[Finding] = run_fn(ctx)
        meta: dict[str, Any] = getattr(mod, "_meta", {})
        return SkillResult(skill_id=manifest.skill_id, findings=findings, meta=meta)
    except Exception as exc:  # noqa: BLE001
        return SkillResult(
            skill_id=manifest.skill_id,
            findings=[
                Finding(
                    rule=manifest.skill_id,
                    severity="fehler",
                    title="Prüfung nicht durchgeführt",
                    detail=str(exc),
                )
            ],
            error=traceback.format_exc(),
        )
