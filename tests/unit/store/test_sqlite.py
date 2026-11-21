"""Tests für LaufStore: CRUD, Context-Roundtrip, Decimal-Präzision."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fibu.contracts import Calc, Context, Finding, Ref
from fibu.skills_runtime import SkillResult
from fibu.store import LaufStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store() -> LaufStore:
    return LaufStore(Path(":memory:"))


@pytest.fixture
def ctx_mit_decimal(make_context):  # type: ignore[no-untyped-def]
    ctx = make_context()
    ctx.changed_accounts = [("1200", "Debitoren", Decimal("12345.67"), Decimal("99999.99"))]
    return ctx


# ---------------------------------------------------------------------------
# Lauf-Lebenszyklus
# ---------------------------------------------------------------------------

def test_erstelle_lauf(store: LaufStore) -> None:
    store.erstelle_lauf("lauf-1", "/pfad/zum/ordner")
    lauf = store.neuester_offener_lauf("/pfad/zum/ordner")
    assert lauf is not None
    assert lauf.lauf_id == "lauf-1"
    assert lauf.status == "laufend"


def test_aktualisiere_status(store: LaufStore) -> None:
    store.erstelle_lauf("lauf-1", "/ordner")
    store.aktualisiere_status("lauf-1", "abgeschlossen")
    lauf = store.neuester_offener_lauf("/ordner")
    assert lauf is None  # abgeschlossen gilt nicht als offen


def test_wartend_gilt_als_offen(store: LaufStore) -> None:
    store.erstelle_lauf("lauf-1", "/ordner")
    store.aktualisiere_status("lauf-1", "wartend")
    lauf = store.neuester_offener_lauf("/ordner")
    assert lauf is not None
    assert lauf.status == "wartend"


def test_neuester_offener_lauf_bei_mehreren(store: LaufStore) -> None:
    store.erstelle_lauf("alt", "/ordner")
    store.aktualisiere_status("alt", "abgeschlossen")
    store.erstelle_lauf("neu", "/ordner")
    lauf = store.neuester_offener_lauf("/ordner")
    assert lauf is not None
    assert lauf.lauf_id == "neu"


def test_alle_laeufe(store: LaufStore) -> None:
    store.erstelle_lauf("a", "/ordner")
    store.erstelle_lauf("b", "/ordner")
    laeufe = store.alle_laeufe("/ordner")
    ids = [l.lauf_id for l in laeufe]
    assert "a" in ids and "b" in ids


# ---------------------------------------------------------------------------
# Context-Roundtrip mit Decimal
# ---------------------------------------------------------------------------

def test_kontext_roundtrip_decimal(store: LaufStore, ctx_mit_decimal: Context) -> None:
    store.erstelle_lauf("lauf-1", "/ordner")
    store.speichere_kontext("lauf-1", ctx_mit_decimal)
    ctx2 = store.lade_kontext("lauf-1")
    assert ctx2.changed_accounts == ctx_mit_decimal.changed_accounts


def test_kontext_decimal_praezision(store: LaufStore, ctx_mit_decimal: Context) -> None:
    """Decimal-Werte müssen verlustfrei erhalten bleiben."""
    store.erstelle_lauf("lauf-1", "/ordner")
    store.speichere_kontext("lauf-1", ctx_mit_decimal)
    ctx2 = store.lade_kontext("lauf-1")
    d_original = ctx_mit_decimal.changed_accounts[0][2]
    d_roundtrip = ctx2.changed_accounts[0][2]
    assert isinstance(d_roundtrip, Decimal)
    assert d_roundtrip == d_original
    assert str(d_roundtrip) == str(d_original)


def test_kontext_nicht_gefunden_wirft_keyerror(store: LaufStore) -> None:
    with pytest.raises(KeyError, match="Kein Kontext"):
        store.lade_kontext("existiert-nicht")


# ---------------------------------------------------------------------------
# Findings-Roundtrip
# ---------------------------------------------------------------------------

def test_findings_roundtrip(store: LaufStore) -> None:
    finding = Finding(
        rule="test",
        severity="fehler",
        title="Testbefund",
        detail="Detail",
        calc=Calc(erwartet=Decimal("100.00"), ist=Decimal("99.00"),
                  differenz=Decimal("1.00"), formel="a - b"),
        refs=[Ref(art="konto", id="3806")],
    )
    results = [SkillResult(skill_id="test-skill", findings=[finding])]
    store.erstelle_lauf("lauf-1", "/ordner")
    store.speichere_findings("lauf-1", results)
    geladen = store.lade_findings("lauf-1")
    assert len(geladen) == 1
    assert geladen[0].skill_id == "test-skill"
    f2 = geladen[0].findings[0]
    assert f2.rule == "test"
    assert isinstance(f2.calc.erwartet, Decimal)  # type: ignore[union-attr]
    assert f2.calc.erwartet == Decimal("100.00")  # type: ignore[union-attr]


def test_findings_id_suffix_roundtrip(store: LaufStore) -> None:
    """id_suffix muss nach dem Roundtrip erhalten bleiben."""
    f = Finding(rule="x", severity="info", title="T", detail="D", id_suffix="#2")
    results = [SkillResult(skill_id="x", findings=[f])]
    store.erstelle_lauf("lauf-1", "/ordner")
    store.speichere_findings("lauf-1", results)
    geladen = store.lade_findings("lauf-1")
    assert geladen[0].findings[0].id_suffix == "#2"


# ---------------------------------------------------------------------------
# Dateirechte (nur wenn echte Datei erstellt wird)
# ---------------------------------------------------------------------------

def test_neue_datei_erhaelt_rechte_0600(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    store = LaufStore(db)
    store.close()
    modus = db.stat().st_mode & 0o777
    assert modus == 0o600, f"Erwartet 0600, erhalten {oct(modus)}"


def test_findings_experimentell_roundtrip(store: LaufStore) -> None:
    """experimentell und deaktiviert überleben den JSON-Roundtrip – scheitert ohne Fix."""
    r = SkillResult(skill_id="exp-skill", findings=[], experimentell=True, deaktiviert=True)
    store.erstelle_lauf("lauf-1", "/ordner")
    store.speichere_findings("lauf-1", [r])
    geladen = store.lade_findings("lauf-1")
    assert geladen[0].experimentell is True   # scheitert ohne Fix in _result_to_dict/_from_dict
    assert geladen[0].deaktiviert is True     # scheitert ohne Fix
