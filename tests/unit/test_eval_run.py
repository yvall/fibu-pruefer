"""Tests für evals/run_eval.py und evals/vergleich.py (reine Funktionen)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module via importlib laden (run_eval.py und vergleich.py sind Skripte)
# ---------------------------------------------------------------------------

_EVALS = Path(__file__).resolve().parents[2] / "evals"


def _load(name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, _EVALS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_re = _load("run_eval")
_vg = _load("vergleich")

_vergleiche          = _re._vergleiche          # type: ignore[attr-defined]
_detail_zu_feldern   = _re._detail_zu_feldern   # type: ignore[attr-defined]
_format_betrag_de_simple = _re._format_betrag_de_simple  # type: ignore[attr-defined]
_erstelle_bericht    = _re._erstelle_bericht    # type: ignore[attr-defined]
_bericht_dateiname   = _re._bericht_dateiname   # type: ignore[attr-defined]
_speichere_bericht   = _re._speichere_bericht   # type: ignore[attr-defined]

_lade_berichte       = _vg._lade_berichte       # type: ignore[attr-defined]
_format_tabelle      = _vg._format_tabelle      # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# _vergleiche
# ---------------------------------------------------------------------------

def test_vergleiche_gleich() -> None:
    assert _vergleiche("152,32", "152,32")


def test_vergleiche_whitespace() -> None:
    assert _vergleiche("  152,32  ", "152,32")


def test_vergleiche_case() -> None:
    assert _vergleiche("ABC-001", "abc-001")


def test_vergleiche_ungleich() -> None:
    assert not _vergleiche("152,32", "120,00")


def test_vergleiche_leer() -> None:
    assert not _vergleiche("152,32", "")


# ---------------------------------------------------------------------------
# _detail_zu_feldern
# ---------------------------------------------------------------------------

def test_detail_alle_felder() -> None:
    detail = "Brutto: 152,32, Betrag-Regel: A: Arithmetik (128,00+24,32=152,32 USt 19%), Datum: 15.03.2024, Nr.: 2024-001"
    f = _detail_zu_feldern(detail)
    assert f["betrag"] == "152,32"
    assert f["datum"] == "15.03.2024"
    assert f["nummer"] == "2024-001"
    assert "betrag_regel" in f


def test_detail_nur_datum() -> None:
    f = _detail_zu_feldern("Datum: 20.08.2026")
    assert f.get("datum") == "20.08.2026"
    assert "betrag" not in f


def test_detail_leer() -> None:
    assert _detail_zu_feldern("") == {}


# ---------------------------------------------------------------------------
# _format_betrag_de_simple
# ---------------------------------------------------------------------------

def test_format_tausender() -> None:
    from decimal import Decimal
    assert _format_betrag_de_simple(Decimal("1234.56")) == "1.234,56"


def test_format_ohne_tausender() -> None:
    from decimal import Decimal
    assert _format_betrag_de_simple(Decimal("100.00")) == "100,00"


def test_format_string_input() -> None:
    assert _format_betrag_de_simple("77.23") == "77,23"


# ---------------------------------------------------------------------------
# _erstelle_bericht
# ---------------------------------------------------------------------------

def _minimal_bericht() -> dict:
    """Erstellt einen minimalen Bericht für Tests."""
    return _erstelle_bericht(
        modell="mistral:latest",
        vorlage_name="vorlage_08 Aug 2026.json",
        n_belege=12,
        laufzeiten=[40.0] * 12,
        gesamt={"betrag": 12, "datum": 12, "nummer": 12},
        treffer={"betrag": 10, "datum": 6, "nummer": 8},
        leer={"betrag": 0, "datum": 1, "nummer": 1},
        base_treffer={"betrag": 4, "datum": 6, "nummer": 10},
        base_leer={"betrag": 1, "datum": 5, "nummer": 2},
        einsatz_gesamt={"betrag": 8, "datum": 6, "nummer": 2},
        einsatz_treffer={"betrag": 6, "datum": 1, "nummer": 1},
        einsatz_leer={"betrag": 0, "datum": 1, "nummer": 0},
    )


def test_bericht_pflichtfelder() -> None:
    b = _minimal_bericht()
    for key in ("datum", "modell", "vorlage", "n_belege",
                "laufzeit_gesamt_s", "laufzeit_avg_s", "felder"):
        assert key in b, f"Schlüssel fehlt: {key}"


def test_bericht_felder_struktur() -> None:
    b = _minimal_bericht()
    for feld in ("betrag", "datum", "nummer"):
        assert feld in b["felder"]
        fd = b["felder"][feld]
        for key in (
            "gesamt", "llm_treffer", "llm_falsch", "llm_leer",
            "base_treffer", "base_falsch", "base_leer",
            "einsatz_gesamt", "einsatz_llm_treffer",
            "einsatz_llm_falsch", "einsatz_llm_leer",
        ):
            assert key in fd, f"Schlüssel {key!r} fehlt in felder[{feld!r}]"


def test_bericht_llm_summe_korrekt() -> None:
    b = _minimal_bericht()
    fd = b["felder"]["betrag"]
    assert fd["llm_treffer"] + fd["llm_falsch"] + fd["llm_leer"] == fd["gesamt"]


def test_bericht_base_summe_korrekt() -> None:
    b = _minimal_bericht()
    fd = b["felder"]["betrag"]
    assert fd["base_treffer"] + fd["base_falsch"] + fd["base_leer"] == fd["gesamt"]


def test_bericht_einsatz_summe_korrekt() -> None:
    b = _minimal_bericht()
    fd = b["felder"]["betrag"]
    assert (
        fd["einsatz_llm_treffer"]
        + fd["einsatz_llm_falsch"]
        + fd["einsatz_llm_leer"]
        == fd["einsatz_gesamt"]
    )


def test_bericht_laufzeit() -> None:
    b = _minimal_bericht()
    assert b["laufzeit_gesamt_s"] == pytest.approx(480.0)
    assert b["laufzeit_avg_s"] == pytest.approx(40.0)


def test_bericht_modell() -> None:
    b = _minimal_bericht()
    assert b["modell"] == "mistral:latest"


# ---------------------------------------------------------------------------
# _bericht_dateiname
# ---------------------------------------------------------------------------

def test_dateiname_format(tmp_path: Path) -> None:
    p = _bericht_dateiname(tmp_path, "2026-11-21", "mistral:latest")
    assert p.name == "bericht_2026-11-21_mistral_latest.json"
    assert p.parent == tmp_path


def test_dateiname_slash_in_modell(tmp_path: Path) -> None:
    p = _bericht_dateiname(tmp_path, "2026-11-21", "org/model:tag")
    assert "/" not in p.name
    assert ":" not in p.name


# ---------------------------------------------------------------------------
# _speichere_bericht
# ---------------------------------------------------------------------------

def test_speichere_bericht_roundtrip(tmp_path: Path) -> None:
    b = _minimal_bericht()
    pfad = tmp_path / "bericht_test.json"
    _speichere_bericht(b, pfad)
    geladen = json.loads(pfad.read_text(encoding="utf-8"))
    assert geladen["modell"] == b["modell"]
    assert geladen["felder"]["betrag"]["llm_treffer"] == b["felder"]["betrag"]["llm_treffer"]


def test_speichere_bericht_erstellt_verzeichnis(tmp_path: Path) -> None:
    b = _minimal_bericht()
    pfad = tmp_path / "subdir" / "bericht_test.json"
    _speichere_bericht(b, pfad)
    assert pfad.exists()


# ---------------------------------------------------------------------------
# _lade_berichte
# ---------------------------------------------------------------------------

def _schreibe_bericht(eval_dir: Path, name: str, datum: str, modell: str) -> None:
    b = _minimal_bericht()
    b["datum"] = datum
    b["modell"] = modell
    (eval_dir / name).write_text(json.dumps(b, indent=2), encoding="utf-8")


def test_lade_berichte_sortiert_absteigend(tmp_path: Path) -> None:
    _schreibe_bericht(tmp_path, "bericht_2026-11-19_a.json", "2026-11-19", "modelA")
    _schreibe_bericht(tmp_path, "bericht_2026-11-21_b.json", "2026-11-21", "modelB")
    _schreibe_bericht(tmp_path, "bericht_2026-11-20_c.json", "2026-11-20", "modelC")
    berichte = _lade_berichte(tmp_path)
    assert len(berichte) == 3
    # Neuester zuerst (alphabetisch absteigend nach Dateiname)
    assert berichte[0]["datum"] == "2026-11-21"
    assert berichte[-1]["datum"] == "2026-11-19"


def test_lade_berichte_leer(tmp_path: Path) -> None:
    assert _lade_berichte(tmp_path) == []


def test_lade_berichte_ignoriert_kaputte_json(tmp_path: Path) -> None:
    (tmp_path / "bericht_2026-11-21_ok.json").write_text(
        json.dumps(_minimal_bericht()), encoding="utf-8"
    )
    (tmp_path / "bericht_2026-11-20_broken.json").write_text(
        "{ kein json }", encoding="utf-8"
    )
    berichte = _lade_berichte(tmp_path)
    assert len(berichte) == 1


def test_lade_berichte_ignoriert_andere_dateien(tmp_path: Path) -> None:
    _schreibe_bericht(tmp_path, "bericht_2026-11-21_x.json", "2026-11-21", "X")
    (tmp_path / "vorlage_08.json").write_text("{}", encoding="utf-8")
    berichte = _lade_berichte(tmp_path)
    assert len(berichte) == 1


# ---------------------------------------------------------------------------
# _format_tabelle
# ---------------------------------------------------------------------------

def test_format_tabelle_leer() -> None:
    t = _format_tabelle([])
    assert "keine" in t.lower()


def test_format_tabelle_enthaelt_modell() -> None:
    b = _minimal_bericht()
    b["datum"] = "2026-11-21"
    b["modell"] = "mistral:latest"
    t = _format_tabelle([b])
    assert "mistral:latest" in t
    assert "2026-11-21" in t


def test_format_tabelle_enthaelt_alle_felder() -> None:
    b = _minimal_bericht()
    t = _format_tabelle([b])
    for feld in ("betrag", "datum", "nummer"):
        assert feld in t


def test_format_tabelle_zwei_spalten(tmp_path: Path) -> None:
    b1 = _minimal_bericht()
    b1["datum"] = "2026-11-21"
    b1["modell"] = "mistral:latest"
    b2 = _minimal_bericht()
    b2["datum"] = "2026-11-20"
    b2["modell"] = "llama3.2"
    t = _format_tabelle([b1, b2])
    assert "mistral:latest" in t
    assert "llama3.2" in t


def test_format_tabelle_enthaelt_einsatz() -> None:
    b = _minimal_bericht()
    t = _format_tabelle([b])
    assert "Einsatz" in t


def test_format_tabelle_enthaelt_laufzeit() -> None:
    b = _minimal_bericht()
    t = _format_tabelle([b])
    assert "Laufzeit" in t or "laufzeit" in t.lower()
