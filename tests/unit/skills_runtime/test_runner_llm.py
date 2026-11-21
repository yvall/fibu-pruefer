"""Tests für LLM-Integration in die Skills-Runtime (Schritt 3b)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fibu.contracts import Auswertung, Context
from fibu.llm import NullLlmClient
from fibu.skills_runtime.loader import SkillManifest
from fibu.skills_runtime.runner import run_one_skill

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ctx() -> Context:
    return Context(auswertung=Auswertung(source="x.pdf", year=2024, month=8))


def _manifest(
    check_path: Path,
    skill_id: str = "test-skill",
    braucht_llm: bool = False,
    llm_optional: bool = False,
    status: str = "stable",
) -> SkillManifest:
    return SkillManifest(
        skill_id=skill_id, check_path=check_path,
        braucht_llm=braucht_llm, llm_optional=llm_optional, status=status,
    )


class _MockLlmClient:
    """Minimaler LlmClient-Mock für Tests."""

    def __init__(self) -> None:
        self.modell = "mock"
        self.aufrufe: list[dict[str, Any]] = []

    def modell_fuer(self, skill_id: str) -> str:
        return self.modell

    def generiere(
        self,
        prompt: str,
        json_schema: dict[str, Any] | None = None,
        **_kwargs: Any,
    ) -> str | None:
        self.aufrufe.append({"prompt": prompt})
        return '{"result": "ok"}'


# ---------------------------------------------------------------------------
# Fallback-Finding (braucht_llm=True + NullLlmClient)
# ---------------------------------------------------------------------------

def test_fallback_finding_severity_info(tmp_path: Path) -> None:
    check_py = tmp_path / "check.py"
    check_py.write_text("def run(ctx, llm): return []\n")
    result = run_one_skill(_manifest(check_py, "llm-skill", braucht_llm=True), _ctx(), NullLlmClient())
    assert len(result.findings) == 1
    assert result.findings[0].severity == "info"


def test_fallback_finding_title(tmp_path: Path) -> None:
    check_py = tmp_path / "check.py"
    check_py.write_text("def run(ctx, llm): return []\n")
    result = run_one_skill(_manifest(check_py, "mein-llm-skill", braucht_llm=True), _ctx(), NullLlmClient())
    assert result.findings[0].title == "LLM nicht konfiguriert"


def test_fallback_finding_detail_enthaelt_skill_id(tmp_path: Path) -> None:
    check_py = tmp_path / "check.py"
    check_py.write_text("def run(ctx, llm): return []\n")
    result = run_one_skill(_manifest(check_py, "mein-llm-skill", braucht_llm=True), _ctx(), NullLlmClient())
    assert "mein-llm-skill" in result.findings[0].detail


def test_fallback_finding_rule_ist_skill_id(tmp_path: Path) -> None:
    check_py = tmp_path / "check.py"
    check_py.write_text("def run(ctx, llm): return []\n")
    result = run_one_skill(_manifest(check_py, "mein-skill", braucht_llm=True), _ctx(), NullLlmClient())
    assert result.findings[0].rule == "mein-skill"


def test_fallback_kein_error_feld(tmp_path: Path) -> None:
    check_py = tmp_path / "check.py"
    check_py.write_text("def run(ctx, llm): return []\n")
    result = run_one_skill(_manifest(check_py, "llm-skill", braucht_llm=True), _ctx(), NullLlmClient())
    assert result.error is None


def test_fallback_importiert_modul_nicht(tmp_path: Path) -> None:
    """check.py mit Absturz-Import – darf nicht importiert werden wenn braucht_llm + NullLlmClient."""
    check_py = tmp_path / "check.py"
    check_py.write_text("raise ImportError('Dieser Import darf nicht passieren')\n")
    result = run_one_skill(_manifest(check_py, "llm-skill", braucht_llm=True), _ctx(), NullLlmClient())
    # Wenn check.py nicht importiert wird, kein error
    assert result.error is None
    assert result.findings[0].title == "LLM nicht konfiguriert"


# ---------------------------------------------------------------------------
# Signatur-Erkennung (braucht_llm=False oder True + echter LLM)
# ---------------------------------------------------------------------------

def test_braucht_llm_false_signatur_1param_kein_llm_arg(tmp_path: Path) -> None:
    """run(ctx) – kein llm-Argument, braucht_llm=False."""
    check_py = tmp_path / "check.py"
    check_py.write_text(
        "from fibu.contracts import Finding\n"
        "def run(ctx):\n"
        "    return [Finding(rule='t', severity='info', title='OK', detail='')]\n"
    )
    result = run_one_skill(_manifest(check_py, braucht_llm=False), _ctx())
    assert result.error is None
    assert result.findings[0].title == "OK"


def test_braucht_llm_true_echtes_llm_ruft_run_mit_llm_auf(tmp_path: Path) -> None:
    """run(ctx, llm) – llm-Argument wird übergeben."""
    check_py = tmp_path / "check.py"
    check_py.write_text(
        "from fibu.contracts import Finding\n"
        "_meta = {}\n"
        "def run(ctx, llm):\n"
        "    _meta['llm_modell'] = llm.modell\n"
        "    return [Finding(rule='t', severity='info', title='Mit-LLM', detail='')]\n"
    )
    mock_llm = _MockLlmClient()
    result = run_one_skill(_manifest(check_py, braucht_llm=True), _ctx(), mock_llm)
    assert result.error is None
    assert result.findings[0].title == "Mit-LLM"
    assert result.meta.get("llm_modell") == "mock"


def test_braucht_llm_false_mit_2params_ergibt_fehler_finding(tmp_path: Path) -> None:
    """braucht_llm=False + run(ctx, llm): Runtime ruft run(ctx) auf → TypeError → Fehler-Finding.

    Dispatch erfolgt ausschließlich über das braucht_llm-Frontmatter-Flag, nicht
    über die Parameteranzahl. Skill mit llm: false muss run(ctx) implementieren.
    """
    check_py = tmp_path / "check.py"
    check_py.write_text(
        "from fibu.contracts import Finding\n"
        "def run(ctx, llm):\n"
        "    return [Finding(rule='t', severity='info', title='LLM-' + llm.modell, detail='')]\n"
    )
    mock_llm = _MockLlmClient()
    result = run_one_skill(_manifest(check_py, braucht_llm=False), _ctx(), mock_llm)
    # run(ctx) mit 2-Parameter-Funktion → TypeError → Fehler-Finding
    assert result.error is not None
    assert result.findings[0].title == "Prüfung nicht durchgeführt"


def test_backward_compat_kein_llm_arg(tmp_path: Path) -> None:
    """Bestehende run_one_skill(manifest, ctx)-Aufrufe ohne llm funktionieren weiterhin."""
    check_py = tmp_path / "check.py"
    check_py.write_text(
        "from fibu.contracts import Finding\n"
        "def run(ctx):\n"
        "    return [Finding(rule='t', severity='info', title='Compat', detail='')]\n"
    )
    result = run_one_skill(_manifest(check_py), _ctx())  # kein llm-Argument
    assert result.error is None
    assert result.findings[0].title == "Compat"


# ---------------------------------------------------------------------------
# run_skills mit llm-Parameter
# ---------------------------------------------------------------------------

def test_run_skills_ohne_llm_parameter(tmp_path: Path) -> None:
    """run_skills() ohne llm – NullLlmClient als Default."""
    from fibu.skills_runtime import run_skills

    d = tmp_path / "sk"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: sk\n---\n")
    (d / "check.py").write_text(
        "from fibu.contracts import Finding\n"
        "def run(ctx):\n"
        "    return [Finding(rule='sk', severity='info', title='OK', detail='')]\n"
    )
    results = run_skills(_ctx(), tmp_path)
    assert len(results) == 1
    assert results[0].findings[0].title == "OK"


def test_run_skills_llm_skill_mit_null_client_gibt_fallback(tmp_path: Path) -> None:
    """LLM-Skill in run_skills() mit NullLlmClient → Fallback-Finding."""
    from fibu.skills_runtime import run_skills

    d = tmp_path / "llm-sk"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: llm-sk\nllm: true\n---\n")
    (d / "check.py").write_text("def run(ctx, llm): return []\n")

    results = run_skills(_ctx(), tmp_path, llm=NullLlmClient())
    assert len(results) == 1
    assert results[0].findings[0].title == "LLM nicht konfiguriert"


def test_run_skills_llm_skill_mit_echtem_client(tmp_path: Path) -> None:
    """LLM-Skill in run_skills() mit echtem (Mock-)LLM läuft durch."""
    from fibu.skills_runtime import run_skills

    d = tmp_path / "llm-sk"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: llm-sk\nllm: true\n---\n")
    (d / "check.py").write_text(
        "from fibu.contracts import Finding\n"
        "def run(ctx, llm):\n"
        "    return [Finding(rule='llm-sk', severity='info', title='LLM-OK', detail='')]\n"
    )
    results = run_skills(_ctx(), tmp_path, llm=_MockLlmClient())
    assert len(results) == 1
    assert results[0].findings[0].title == "LLM-OK"
    assert results[0].error is None


def test_run_skills_mixed_llm_und_normaler_skill(tmp_path: Path) -> None:
    """Mix aus LLM-Skill (Fallback) und normalem Skill – beide laufen durch."""
    from fibu.skills_runtime import run_skills

    for skill_id, llm_flag, body in [
        ("normal", "", "from fibu.contracts import Finding\ndef run(ctx): return [Finding(rule='normal', severity='info', title='N', detail='')]\n"),
        ("llm-skill", "llm: true\n", "def run(ctx, llm): return []\n"),
    ]:
        d = tmp_path / skill_id
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {skill_id}\n{llm_flag}---\n")
        (d / "check.py").write_text(body)

    results = run_skills(_ctx(), tmp_path, llm=NullLlmClient())
    assert len(results) == 2
    normal_r = next(r for r in results if r.skill_id == "normal")
    llm_r = next(r for r in results if r.skill_id == "llm-skill")
    assert normal_r.findings[0].title == "N"
    assert llm_r.findings[0].title == "LLM nicht konfiguriert"


# ---------------------------------------------------------------------------
# Experimentelle Skills (status: experimental)
# ---------------------------------------------------------------------------

def test_experimentell_deaktiviert_keine_findings(tmp_path: Path) -> None:
    """Experimenteller Skill mit experimentelle_aktiv=False → keine Findings."""
    check_py = tmp_path / "check.py"
    check_py.write_text("raise AssertionError('darf nicht importiert werden')\n")
    result = run_one_skill(
        _manifest(check_py, "exp-skill", braucht_llm=True, status="experimental"),
        _ctx(),
        NullLlmClient(),
        experimentelle_aktiv=False,
    )
    assert result.findings == []
    assert result.error is None


def test_experimentell_deaktiviert_flags(tmp_path: Path) -> None:
    """Deaktivierter experimenteller Skill setzt experimentell=True, deaktiviert=True."""
    check_py = tmp_path / "check.py"
    check_py.write_text("")
    result = run_one_skill(
        _manifest(check_py, "exp", status="experimental"),
        _ctx(),
        experimentelle_aktiv=False,
    )
    assert result.experimentell is True
    assert result.deaktiviert is True


def test_experimentell_deaktiviert_importiert_nicht(tmp_path: Path) -> None:
    """check.py mit Absturz-Import darf nicht importiert werden wenn deaktiviert."""
    check_py = tmp_path / "check.py"
    check_py.write_text("raise ImportError('Dieser Import darf nicht passieren')\n")
    result = run_one_skill(
        _manifest(check_py, "exp", status="experimental"),
        _ctx(),
        experimentelle_aktiv=False,
    )
    assert result.error is None


def test_experimentell_aktiv_laeuft_durch(tmp_path: Path) -> None:
    """Experimenteller Skill mit experimentelle_aktiv=True läuft normal."""
    check_py = tmp_path / "check.py"
    check_py.write_text(
        "from fibu.contracts import Finding\n"
        "def run(ctx, llm):\n"
        "    return [Finding(rule='exp', severity='info', title='Exp-OK', detail='')]\n"
    )
    result = run_one_skill(
        _manifest(check_py, "exp", braucht_llm=True, status="experimental"),
        _ctx(),
        _MockLlmClient(),
        experimentelle_aktiv=True,
    )
    assert result.findings[0].title == "Exp-OK"
    assert result.experimentell is True
    assert result.deaktiviert is False


def test_experimentell_aktiv_setzt_flag(tmp_path: Path) -> None:
    """Aktiv ausgeführter experimenteller Skill hat experimentell=True."""
    check_py = tmp_path / "check.py"
    check_py.write_text("def run(ctx): return []\n")
    result = run_one_skill(
        _manifest(check_py, "exp", status="experimental"),
        _ctx(),
        experimentelle_aktiv=True,
    )
    assert result.experimentell is True
    assert result.deaktiviert is False


def test_stable_skill_nicht_als_experimentell_markiert(tmp_path: Path) -> None:
    """Normaler Skill hat experimentell=False."""
    check_py = tmp_path / "check.py"
    check_py.write_text("def run(ctx): return []\n")
    result = run_one_skill(_manifest(check_py, "normal"), _ctx())
    assert result.experimentell is False
    assert result.deaktiviert is False


# ---------------------------------------------------------------------------
# llm: optional – NullLlmClient wird durchgereicht, kein Abbruch
# ---------------------------------------------------------------------------

def test_llm_optional_null_client_kein_abbruch(tmp_path: Path) -> None:
    """llm_optional=True + NullLlmClient → kein 'LLM nicht konfiguriert'-Finding."""
    check_py = tmp_path / "check.py"
    check_py.write_text(
        "from fibu.contracts import Finding\n"
        "def run(ctx, llm): return [Finding(rule='t', severity='info', title='Optional-OK', detail='')]\n"
    )
    result = run_one_skill(_manifest(check_py, llm_optional=True), _ctx(), NullLlmClient())
    assert result.error is None
    assert result.findings[0].title == "Optional-OK"


def test_llm_optional_null_client_erhaelt_null_client(tmp_path: Path) -> None:
    """llm_optional + NullLlmClient → check.py erhält NullLlmClient-Instanz."""
    check_py = tmp_path / "check.py"
    check_py.write_text(
        "from fibu.contracts import Finding\n"
        "from fibu.llm import NullLlmClient\n"
        "_meta = {}\n"
        "def run(ctx, llm):\n"
        "    _meta['ist_null'] = isinstance(llm, NullLlmClient)\n"
        "    return []\n"
    )
    result = run_one_skill(_manifest(check_py, llm_optional=True), _ctx(), NullLlmClient())
    assert result.error is None
    assert result.meta.get("ist_null") is True


def test_llm_optional_mit_echtem_client(tmp_path: Path) -> None:
    """llm_optional + echter LLM-Client → läuft normal durch."""
    check_py = tmp_path / "check.py"
    check_py.write_text(
        "from fibu.contracts import Finding\n"
        "def run(ctx, llm):\n"
        "    return [Finding(rule='t', severity='info', title=llm.modell, detail='')]\n"
    )
    result = run_one_skill(_manifest(check_py, llm_optional=True), _ctx(), _MockLlmClient())
    assert result.error is None
    assert result.findings[0].title == "mock"


def test_llm_true_null_client_abbruch_unveraendert(tmp_path: Path) -> None:
    """braucht_llm=True + NullLlmClient → weiterhin früher Abbruch."""
    check_py = tmp_path / "check.py"
    check_py.write_text("raise AssertionError('Darf nicht laufen')\n")
    result = run_one_skill(_manifest(check_py, braucht_llm=True), _ctx(), NullLlmClient())
    assert result.findings[0].title == "LLM nicht konfiguriert"
    assert result.error is None


def test_run_skills_llm_optional_mit_null_client(tmp_path: Path) -> None:
    """run_skills() mit llm: optional + NullLlmClient → kein Fallback-Finding."""
    from fibu.skills_runtime import run_skills

    d = tmp_path / "opt-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: opt-skill\nllm: optional\n---\n")
    (d / "check.py").write_text(
        "from fibu.contracts import Finding\n"
        "def run(ctx, llm):\n"
        "    return [Finding(rule='opt-skill', severity='info', title='Deterministisch', detail='')]\n"
    )
    results = run_skills(_ctx(), tmp_path, llm=NullLlmClient())
    assert len(results) == 1
    assert results[0].findings[0].title == "Deterministisch"


def test_run_skills_experimentell_deaktiviert_per_default(tmp_path: Path) -> None:
    """run_skills() ohne experimentelle_aktiv → experimenteller Skill liefert keine Findings."""
    from fibu.skills_runtime import run_skills

    d = tmp_path / "exp-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: exp-skill\nllm: true\nstatus: experimental\n---\n")
    (d / "check.py").write_text("raise AssertionError('darf nicht laufen')\n")

    results = run_skills(_ctx(), tmp_path, llm=NullLlmClient())
    assert len(results) == 1
    r = results[0]
    assert r.findings == []
    assert r.deaktiviert is True


def test_run_skills_experimentell_aktiv_schalter(tmp_path: Path) -> None:
    """run_skills() mit experimentelle_aktiv=True → experimenteller LLM-Skill bekommt Fallback."""
    from fibu.skills_runtime import run_skills

    d = tmp_path / "exp-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: exp-skill\nllm: true\nstatus: experimental\n---\n")
    (d / "check.py").write_text("def run(ctx, llm): return []\n")

    # Mit NullLlmClient und aktivem Schalter: Skill läuft, bekommt Fallback-Finding
    results = run_skills(_ctx(), tmp_path, llm=NullLlmClient(), experimentelle_aktiv=True)
    assert len(results) == 1
    assert results[0].findings[0].title == "LLM nicht konfiguriert"
    assert results[0].deaktiviert is False


# ---------------------------------------------------------------------------
# experimentell-Flag in Fehlerpfaden (je Test scheitert ohne den Fix)
# ---------------------------------------------------------------------------

def test_e7_fallback_experimentell_flag_gesetzt(tmp_path: Path) -> None:
    """E7-Fallback (braucht_llm + NullLlmClient) setzt experimentell – scheitert ohne Fix."""
    check_py = tmp_path / "check.py"
    check_py.write_text("def run(ctx, llm): return []\n")
    result = run_one_skill(
        _manifest(check_py, "exp-llm", braucht_llm=True, status="experimental"),
        _ctx(),
        NullLlmClient(),
        experimentelle_aktiv=True,  # Schalter aktiv → E7-Pfad, kein Deaktiviert-Pfad
    )
    assert result.findings[0].title == "LLM nicht konfiguriert"
    assert result.experimentell is True  # scheitert ohne Fix


def test_check_py_fehlt_experimentell_flag_gesetzt(tmp_path: Path) -> None:
    """check.py nicht gefunden + experimenteller Skill → experimentell=True gesetzt."""
    result = run_one_skill(
        _manifest(tmp_path / "nonexistent.py", "exp-skill", status="experimental"),
        _ctx(),
        experimentelle_aktiv=True,
    )
    assert result.error is not None
    assert result.experimentell is True  # scheitert ohne Fix


def test_exception_handler_experimentell_flag_gesetzt(tmp_path: Path) -> None:
    """Laufzeitfehler in check.py + experimenteller Skill → experimentell=True gesetzt."""
    check_py = tmp_path / "check.py"
    check_py.write_text("def run(ctx): raise ValueError('Absturz')\n")
    result = run_one_skill(
        _manifest(check_py, "exp-skill", status="experimental"),
        _ctx(),
        experimentelle_aktiv=True,
    )
    assert result.error is not None
    assert result.experimentell is True  # scheitert ohne Fix
