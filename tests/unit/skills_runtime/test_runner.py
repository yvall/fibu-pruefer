from decimal import Decimal
from pathlib import Path

import pytest

from fibu.contracts import Auswertung, Context, Finding
from fibu.skills_runtime.loader import SkillManifest
from fibu.skills_runtime.runner import run_one_skill


def _ctx() -> Context:
    return Context(auswertung=Auswertung(source="x.pdf", year=2024, month=8))


def _manifest(check_path: Path, skill_id: str = "test-skill") -> SkillManifest:
    return SkillManifest(skill_id=skill_id, check_path=check_path)


def test_run_one_skill_success(tmp_path: Path) -> None:
    check_py = tmp_path / "check.py"
    check_py.write_text(
        "from fibu.contracts import Finding\n"
        "def run(ctx):\n"
        "    return [Finding(rule='test-skill', severity='info', title='OK', detail='')]\n"
    )
    result = run_one_skill(_manifest(check_py), _ctx())
    assert result.error is None
    assert len(result.findings) == 1
    assert result.findings[0].severity == "info"
    assert result.findings[0].rule == "test-skill"


def test_run_one_skill_no_findings(tmp_path: Path) -> None:
    check_py = tmp_path / "check.py"
    check_py.write_text("def run(ctx): return []\n")
    result = run_one_skill(_manifest(check_py), _ctx())
    assert result.error is None
    assert result.findings == []


def test_run_one_skill_crash(tmp_path: Path) -> None:
    check_py = tmp_path / "check.py"
    check_py.write_text("def run(ctx): raise ValueError('Absichtlicher Fehler')\n")
    result = run_one_skill(_manifest(check_py), _ctx())
    assert result.error is not None
    assert "Absichtlicher Fehler" in result.error
    assert len(result.findings) == 1
    assert result.findings[0].title == "Prüfung nicht durchgeführt"
    assert result.findings[0].severity == "fehler"
    assert result.skill_id == "test-skill"


def test_run_one_skill_missing_check_py(tmp_path: Path) -> None:
    missing = tmp_path / "check.py"  # existiert nicht
    result = run_one_skill(_manifest(missing), _ctx())
    assert result.error is not None
    assert result.findings[0].title == "Prüfung nicht durchgeführt"


def test_run_one_skill_missing_run_function(tmp_path: Path) -> None:
    check_py = tmp_path / "check.py"
    check_py.write_text("# keine run()-Funktion\n")
    result = run_one_skill(_manifest(check_py), _ctx())
    assert result.error is not None
    assert result.findings[0].title == "Prüfung nicht durchgeführt"


def test_run_skills_integration(tmp_path: Path) -> None:
    """Vollständiger Durchlauf mit run_skills(): zwei unabhängige Skills."""
    from fibu.skills_runtime import run_skills

    for skill_id, body in [
        ("skill-a", "from fibu.contracts import Finding\ndef run(ctx): return [Finding(rule='skill-a', severity='info', title='A', detail='')]\n"),
        ("skill-b", "from fibu.contracts import Finding\ndef run(ctx): return [Finding(rule='skill-b', severity='pruefen', title='B', detail='')]\n"),
    ]:
        d = tmp_path / skill_id
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {skill_id}\n---\n")
        (d / "check.py").write_text(body)

    results = run_skills(_ctx(), tmp_path)
    assert len(results) == 2
    all_findings = [f for r in results for f in r.findings]
    assert any(f.rule == "skill-a" for f in all_findings)
    assert any(f.rule == "skill-b" for f in all_findings)


def test_run_skills_respects_order(tmp_path: Path) -> None:
    """Skills mit runs_after laufen nach ihren Abhängigkeiten."""
    from fibu.skills_runtime import run_skills

    execution_order: list[str] = []

    for skill_id, runs_after, body in [
        ("first", "", ""),
        ("second", "runs_after:\n  - first\n", ""),
    ]:
        d = tmp_path / skill_id
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {skill_id}\n{runs_after}---\n")
        (d / "check.py").write_text("def run(ctx): return []\n")

    results = run_skills(_ctx(), tmp_path)
    assert len(results) == 2
    # Beide müssen ohne Fehler durchlaufen
    assert all(r.error is None for r in results)


def test_run_skills_error_does_not_abort(tmp_path: Path) -> None:
    """Ein crashender Skill stoppt nicht die anderen."""
    from fibu.skills_runtime import run_skills

    for skill_id, body in [
        ("crash-skill", "def run(ctx): raise RuntimeError('Absturz')"),
        ("ok-skill", "from fibu.contracts import Finding\ndef run(ctx): return [Finding(rule='ok-skill', severity='info', title='OK', detail='')]"),
    ]:
        d = tmp_path / skill_id
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {skill_id}\n---\n")
        (d / "check.py").write_text(body)

    results = run_skills(_ctx(), tmp_path)
    assert len(results) == 2
    crash_result = next(r for r in results if r.skill_id == "crash-skill")
    ok_result = next(r for r in results if r.skill_id == "ok-skill")
    assert crash_result.error is not None
    assert ok_result.error is None
    assert ok_result.findings[0].title == "OK"
