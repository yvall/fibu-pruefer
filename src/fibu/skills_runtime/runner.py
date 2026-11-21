from __future__ import annotations

import importlib.abc
import importlib.util
import traceback
from dataclasses import dataclass, field
from typing import Any

from fibu.contracts import Context, Finding
from fibu.llm import LlmClient, NullLlmClient

from .loader import SkillManifest


@dataclass
class SkillResult:
    skill_id: str
    findings: list[Finding] = field(default_factory=list)
    # Optionale Metadaten, die der Skill an die Runtime zurückgeben kann
    # (z. B. changed_accounts nach vormonat-fortschreibung).
    meta: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    experimentell: bool = False   # True wenn manifest.status == "experimental"
    deaktiviert: bool = False     # True wenn experimentell und experimentelle_aktiv=False


def run_one_skill(
    manifest: SkillManifest,
    ctx: Context,
    llm: LlmClient | None = None,
    experimentelle_aktiv: bool = False,
) -> SkillResult:
    """Führt einen einzelnen Skill aus. Fehler erzeugen ein Finding und brechen den Lauf nicht ab."""
    ist_experimentell = manifest.status == "experimental"
    effective_llm: LlmClient = llm if llm is not None else NullLlmClient()

    # Experimentelle Skills werden übersprungen, wenn der Schalter inaktiv ist.
    # Kein Befund, kein Modellaufruf, kein Import.
    if ist_experimentell and not experimentelle_aktiv:
        return SkillResult(
            skill_id=manifest.skill_id,
            experimentell=True,
            deaktiviert=True,
        )

    # E7: Fallback-Check vor Modulimport – LLM-Skill ohne LLM gibt info-Finding
    if manifest.braucht_llm and isinstance(effective_llm, NullLlmClient):
        return SkillResult(
            skill_id=manifest.skill_id,
            findings=[
                Finding(
                    rule=manifest.skill_id,
                    severity="info",
                    title="LLM nicht konfiguriert",
                    detail=(
                        f"Skill {manifest.skill_id} benötigt ein LLM-Modell "
                        f"– kein Modell konfiguriert."
                    ),
                )
            ],
            experimentell=ist_experimentell,
        )

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
            experimentell=ist_experimentell,
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

        # E6: Dispatch per Frontmatter-Flag; llm_optional = NullLlmClient erlaubt
        if manifest.braucht_llm or manifest.llm_optional:
            findings: list[Finding] = run_fn(ctx, effective_llm)
        else:
            findings = run_fn(ctx)

        meta: dict[str, Any] = getattr(mod, "_meta", {})
        return SkillResult(
            skill_id=manifest.skill_id,
            findings=findings,
            meta=meta,
            experimentell=ist_experimentell,
        )
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
            experimentell=ist_experimentell,
        )
