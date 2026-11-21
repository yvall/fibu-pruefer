"""Tests für den KI-gestützt-Abschnitt in report.py (experimentelle Skills)."""
from __future__ import annotations

from fibu.contracts import Auswertung, Finding
from fibu.report import to_markdown
from fibu.skills_runtime.runner import SkillResult


def _auswertung() -> Auswertung:
    return Auswertung(source="test.pdf", year=2024, month=8)


def _result(
    skill_id: str = "beleg-extraktion",
    findings: list[Finding] | None = None,
    experimentell: bool = False,
    deaktiviert: bool = False,
) -> SkillResult:
    return SkillResult(
        skill_id=skill_id,
        findings=findings or [],
        experimentell=experimentell,
        deaktiviert=deaktiviert,
    )


# ---------------------------------------------------------------------------
# Kein experimenteller Skill → kein KI-gestützt-Abschnitt
# ---------------------------------------------------------------------------

def test_kein_ki_abschnitt_wenn_kein_experimenteller_skill() -> None:
    r = _result("normaler-skill", experimentell=False)
    md = to_markdown(_auswertung(), [r])
    assert "KI-gestützt" not in md


# ---------------------------------------------------------------------------
# Experimenteller Skill deaktiviert → Hinweis
# ---------------------------------------------------------------------------

def test_hinweis_bei_deaktiviertem_skill() -> None:
    r = _result(experimentell=True, deaktiviert=True)
    md = to_markdown(_auswertung(), [r])
    assert "KI-gestützt" in md
    assert "deaktiviert" in md


def test_hinweis_enthaelt_skill_id() -> None:
    r = _result("beleg-extraktion", experimentell=True, deaktiviert=True)
    md = to_markdown(_auswertung(), [r])
    assert "beleg-extraktion" in md


def test_keine_dopplung_deaktivierter_findings_in_hauptabschnitt() -> None:
    """Deaktivierter Skill hat keine Findings – nichts in den Haupt-Abschnitten."""
    r = _result(experimentell=True, deaktiviert=True)
    md = to_markdown(_auswertung(), [r])
    assert "🔵 Hinweise" not in md or "beleg-extraktion" not in md.split("KI-gestützt")[0]


# ---------------------------------------------------------------------------
# Experimenteller Skill aktiv → (experimentell)-Label
# ---------------------------------------------------------------------------

def test_experimentell_label_bei_aktivem_skill() -> None:
    finding = Finding(
        rule="beleg-extraktion", severity="info",
        title="Felder extrahiert", detail="Brutto: 100,00",
    )
    r = _result(findings=[finding], experimentell=True, deaktiviert=False)
    md = to_markdown(_auswertung(), [r])
    assert "KI-gestützt" in md
    assert "experimentell" in md


def test_aktiver_experimenteller_skill_zeigt_findings() -> None:
    finding = Finding(
        rule="beleg-extraktion", severity="info",
        title="Felder extrahiert", detail="Betrag: 500,00",
    )
    r = _result(findings=[finding], experimentell=True, deaktiviert=False)
    md = to_markdown(_auswertung(), [r])
    assert "Felder extrahiert" in md
    assert "Betrag: 500,00" in md


def test_aktiver_ohne_findings_zeigt_keine_befunde() -> None:
    r = _result(findings=[], experimentell=True, deaktiviert=False)
    md = to_markdown(_auswertung(), [r])
    assert "KI-gestützt" in md
    assert "Keine Befunde" in md


# ---------------------------------------------------------------------------
# Gemischte Situation: ein deaktiviert, einer aktiv
# ---------------------------------------------------------------------------

def test_gemischt_deaktiviert_und_aktiv() -> None:
    r_deak = _result("skill-a", experimentell=True, deaktiviert=True)
    r_aktiv = _result(
        "skill-b",
        findings=[Finding(rule="skill-b", severity="info", title="B-OK", detail="")],
        experimentell=True,
        deaktiviert=False,
    )
    md = to_markdown(_auswertung(), [r_deak, r_aktiv])
    assert "deaktiviert" in md
    assert "skill-a" in md
    assert "skill-b" in md
    assert "B-OK" in md
