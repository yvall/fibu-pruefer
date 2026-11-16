"""Tests für Finding.id: Stabilität, Normalisierung, Deduplication."""
from __future__ import annotations

from decimal import Decimal

from fibu.contracts import Calc, Finding, Ref
from fibu.graph.nodes import _dedupliziere_finding_ids
from fibu.skills_runtime import SkillResult

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _f(rule: str = "test", title: str = "T", refs: list[Ref] | None = None,
       formel: str = "", **kw: object) -> Finding:
    calc = Calc(erwartet=Decimal(1), ist=Decimal(1), differenz=Decimal(0),
                formel=formel) if formel else None
    return Finding(rule=rule, severity="info", title=title, detail="D",
                   refs=refs or [], calc=calc, **kw)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Stabilität
# ---------------------------------------------------------------------------

def test_gleiche_eingabe_gleiche_id() -> None:
    f1 = _f(rule="x", title="Gleicher Titel")
    f2 = _f(rule="x", title="Gleicher Titel")
    assert f1.id == f2.id


def test_unterschiedliche_regel_verschiedene_id() -> None:
    f1 = _f(rule="regel-a", title="T")
    f2 = _f(rule="regel-b", title="T")
    assert f1.id != f2.id


def test_schema_version_ist_2() -> None:
    assert Finding(rule="x", severity="info", title="T", detail="D").schema_version == "2"


# ---------------------------------------------------------------------------
# Refs-Pfad
# ---------------------------------------------------------------------------

def test_refs_bestimmen_id() -> None:
    refs = [Ref(art="konto", id="4000")]
    f = _f(refs=refs)
    assert f.id  # nicht leer
    # Andere ref → andere ID
    f2 = _f(refs=[Ref(art="konto", id="9999")])
    assert f.id != f2.id


def test_refs_sortierung_irrelevant() -> None:
    r1 = Ref(art="konto", id="1200")
    r2 = Ref(art="konto", id="3300")
    f_ab = _f(refs=[r1, r2])
    f_ba = _f(refs=[r2, r1])
    assert f_ab.id == f_ba.id


# ---------------------------------------------------------------------------
# Formel-Fallback: Ziffern werden normalisiert
# ---------------------------------------------------------------------------

def test_gleicher_befund_anderer_betrag_gleiche_id() -> None:
    """Kernanforderung: gleicher Prüftyp, anderer Betrag → gleiche ID."""
    f_jan = _f(rule="bwa-rechenwege", formel="Summe Debitoren 1234.56 ≠ Sammelkonto 1200.00")
    f_feb = _f(rule="bwa-rechenwege", formel="Summe Debitoren 9999.99 ≠ Sammelkonto 9800.00")
    assert f_jan.id == f_feb.id


def test_unterschiedliche_formel_verschiedene_id() -> None:
    f1 = _f(rule="x", formel="Konto A ≠ Konto B")
    f2 = _f(rule="x", formel="Konto C ≠ Konto D")
    assert f1.id != f2.id


# ---------------------------------------------------------------------------
# Titel-Fallback: Ziffern werden normalisiert
# ---------------------------------------------------------------------------

def test_titel_fallback_normalisiert_ziffern() -> None:
    f_a = _f(rule="x", title="Differenz in Konto 3806: 100,00 €")
    f_b = _f(rule="x", title="Differenz in Konto 3806: 999,99 €")
    assert f_a.id == f_b.id


def test_titel_fallback_unterschiedliche_konten() -> None:
    f_a = _f(rule="x", title="Differenz in Konto Debitoren")
    f_b = _f(rule="x", title="Differenz in Konto Kreditoren")
    assert f_a.id != f_b.id


# ---------------------------------------------------------------------------
# id_suffix
# ---------------------------------------------------------------------------

def test_id_suffix_wird_angehaengt() -> None:
    f = _f(rule="x", title="T")
    f2 = f.model_copy(update={"id_suffix": "#2"})
    assert f2.id == f.id + "#2"
    assert f.id != f2.id


# ---------------------------------------------------------------------------
# Deduplizierung in _dedupliziere_finding_ids
# ---------------------------------------------------------------------------

def test_keine_kollision_keine_info_finding() -> None:
    r1 = SkillResult(skill_id="a", findings=[_f(rule="x", title="Eins"),
                                              _f(rule="x", title="Zwei")])
    dedup, infos = _dedupliziere_finding_ids([r1])
    assert infos == []
    assert len(dedup[0].findings) == 2


def test_kollision_bekommt_suffix() -> None:
    # Zwei Findings mit identischem Schlüssel (gleiche Regel, gleicher Titel ohne Zahlen)
    f_gleich = _f(rule="gleich", title="Exakt gleicher Titel")
    r = SkillResult(skill_id="a", findings=[f_gleich, f_gleich])
    dedup, infos = _dedupliziere_finding_ids([r])
    ids = [f.id for f in dedup[0].findings]
    assert ids[0] != ids[1]
    assert ids[1].endswith("#2")
    assert len(infos) == 1
    assert infos[0].severity == "info"


def test_kollision_ueber_skills_hinweg() -> None:
    f = _f(rule="doppelt", title="Gleicher Titel")
    r1 = SkillResult(skill_id="skill-a", findings=[f])
    r2 = SkillResult(skill_id="skill-b", findings=[f])
    dedup, infos = _dedupliziere_finding_ids([r1, r2])
    id_a = dedup[0].findings[0].id
    id_b = dedup[1].findings[0].id
    assert id_a != id_b
    assert id_b.endswith("#2")
    assert len(infos) == 1
