"""Wiederverwendbarer Helfer für Migrationsparität: Legacy-Check vs. Skill.

Verwendung in einem Migrationstest:

    from legacy.fibu_pruefer.checks import check_bwa_arithmetik
    from tests.migration_parity import assert_migration_parity, load_skill_run

    _skill_run = load_skill_run("bwa-rechenwege")

    def test_parity(make_context):
        ctx = make_context(bwa={...})
        assert_migration_parity(check_bwa_arithmetik, _skill_run, ctx)
"""
from __future__ import annotations

import difflib
import importlib.abc
import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fibu.contracts import Context, Finding

# Absoluter Pfad zu skills/ relativ zu dieser Datei (tests/migration_parity.py → tests/ → Projektwurzel).
_DEFAULT_SKILLS_DIR: Path = Path(__file__).resolve().parent.parent / "skills"


def load_skill_run(
    skill_id: str,
    skills_dir: Path = _DEFAULT_SKILLS_DIR,
) -> Callable[[Context], list[Finding]]:
    """Lädt die run()-Funktion eines Code-Skills per Skill-ID."""
    check_path = skills_dir / skill_id / "check.py"
    spec = importlib.util.spec_from_file_location(
        f"_migparity_{skill_id.replace('-', '_')}", check_path
    )
    if spec is None or not isinstance(spec.loader, importlib.abc.Loader):
        raise ImportError(f"Skill {skill_id!r}: check.py nicht ladbar unter {check_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run  # type: ignore[no-any-return]


def _normalize_legacy(result: Any) -> list[dict[str, str]]:
    return sorted(
        [{"severity": f.severity, "title": f.title, "detail": f.detail} for f in result.findings],
        key=lambda x: (x["severity"], x["title"]),
    )


def _normalize_new(findings: list[Finding]) -> list[dict[str, str]]:
    return sorted(
        [{"severity": f.severity, "title": f.title, "detail": f.detail} for f in findings],
        key=lambda x: (x["severity"], x["title"]),
    )


def assert_migration_parity(
    legacy_fn: Callable[[Any], Any],
    skill_run: Callable[[Context], list[Finding]],
    ctx: Context,
) -> None:
    """Prüft, dass legacy_fn und skill_run dieselben Befunde liefern.

    legacy_fn erhält ctx.auswertung per Duck-Typing: funktioniert, solange die
    aufgerufene Funktion nur Felder nutzt, die in contracts.Auswertung vorhanden sind.
    Verglichen werden severity, title und detail – nicht rule oder refs, da diese
    zwischen Legacy (hat keines) und Skill (hat beide) strukturell verschieden sind.
    """
    legacy_result = legacy_fn(ctx.auswertung)
    expected = _normalize_legacy(legacy_result)
    actual = _normalize_new(skill_run(ctx))

    if expected == actual:
        return

    only_legacy = [f for f in expected if f not in actual]
    only_skill = [f for f in actual if f not in expected]

    exp_lines = json.dumps(expected, ensure_ascii=False, indent=2).splitlines()
    act_lines = json.dumps(actual, ensure_ascii=False, indent=2).splitlines()
    diff = "\n".join(
        difflib.unified_diff(exp_lines, act_lines, fromfile="legacy", tofile="skill", lineterm="")
    )

    summary = (
        f"Parität verletzt: {len(only_legacy)} Befund(e) fehlen im Skill,"
        f" {len(only_skill)} Befund(e) nur im Skill."
    )
    parts = [summary]
    if only_legacy:
        parts.append(f"\nNur im Legacy ({len(only_legacy)}):")
        parts.extend(f"  - {f}" for f in only_legacy)
    if only_skill:
        parts.append(f"\nNur im Skill ({len(only_skill)}):")
        parts.extend(f"  + {f}" for f in only_skill)
    parts.append(f"\nDiff:\n{diff}")

    raise AssertionError("\n".join(parts))
