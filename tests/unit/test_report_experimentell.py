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


# ---------------------------------------------------------------------------
# Experimentelle Findings NUR in KI-gestützt (Nachbesserung)
# ---------------------------------------------------------------------------

def test_aktiver_exp_finding_nicht_in_hinweise() -> None:
    """Info-Finding eines aktiven experimentellen Skills steht NICHT in Hinweise."""
    exp_f = Finding(rule="re", severity="info", title="Rückfrage XYZ", detail="Detail")
    normal_f = Finding(rule="k", severity="info", title="Klärung", detail="X")
    r_exp = _result("re", findings=[exp_f], experimentell=True)
    r_normal = _result("k", findings=[normal_f], experimentell=False)

    md = to_markdown(_auswertung(), [r_normal, r_exp])

    # Experimentelles Finding im KI-gestützt
    assert "🤖 KI-gestützt" in md
    ki_idx = md.index("🤖 KI-gestützt")
    assert "Rückfrage XYZ" in md[ki_idx:]

    # NICHT in Hinweise-Block vor KI-gestützt
    assert "Rückfrage XYZ" not in md[:ki_idx]


def test_hinweise_zaehler_ohne_experimentelle() -> None:
    """Hinweis-Zähler reflektiert nur nicht-experimentelle Findings."""
    exp_f = Finding(rule="re", severity="info", title="Experimentell", detail="")
    normal_f = Finding(rule="k", severity="info", title="Normal", detail="")
    r_exp = _result("re", findings=[exp_f], experimentell=True)
    r_normal = _result("k", findings=[normal_f], experimentell=False)

    md_nur_normal = to_markdown(_auswertung(), [r_normal])
    md_mit_exp = to_markdown(_auswertung(), [r_normal, r_exp])

    import re as re_mod
    z_normal = re_mod.search(r'Hinweise \((\d+)\)', md_nur_normal)
    z_mit_exp = re_mod.search(r'Hinweise \((\d+)\)', md_mit_exp)

    assert z_normal is not None and z_mit_exp is not None
    assert z_normal.group(1) == z_mit_exp.group(1) == "1"


def test_n_findings_zaehler_ohne_experimentelle() -> None:
    """Der Gesamt-Findings-Zähler im Header zählt nur nicht-experimentelle."""
    exp_f = Finding(rule="re", severity="info", title="Exp", detail="")
    normal_f = Finding(rule="k", severity="info", title="Normal", detail="")
    r_exp = _result("re", findings=[exp_f], experimentell=True)
    r_normal = _result("k", findings=[normal_f], experimentell=False)

    md = to_markdown(_auswertung(), [r_normal, r_exp])

    # Header: "1 Skills, 1 Befunde" (nur der normale Skill)
    assert "1 Skills, 1 Befunde" in md


def test_overall_severity_ohne_experimentelle() -> None:
    """overall_severity ignoriert experimentelle Findings."""
    from fibu.report import overall_severity
    exp_f = Finding(rule="re", severity="fehler", title="Exp", detail="")
    r_exp = _result("re", findings=[exp_f], experimentell=True)
    # Nur experimentelles fehler-Finding → sollte "ok" ergeben
    assert overall_severity([r_exp]) == "ok"


def test_exp_skill_mit_fehler_in_ki_gestuetzt() -> None:
    """Skill-Fehler eines experimentellen Skills steht in KI-gestützt, nicht in Skill-Fehler."""
    r_exp = _result("re", experimentell=True)
    r_exp.error = "Laufzeitfehler"
    r_exp.findings = []

    md = to_markdown(_auswertung(), [r_exp])

    ki_idx = md.index("🤖 KI-gestützt")
    assert "Laufzeitfehler" in md[ki_idx:]
    # Nicht im ⚠️ Skill-Fehler-Abschnitt (falls vorhanden, wäre es vor KI-gestützt)
    assert "Laufzeitfehler" not in md[:ki_idx]
