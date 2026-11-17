"""End-to-End-Tests für fibu eval vorlage und run_eval.py-Kompatibilität.

Prüft:
- Hilfsfunktionen _format_betrag_de, _beleg_zu_vorlage_eintrag, _eval_ausgabe_pfad
- Dateinamen-Konsistenz zwischen CLI (Schreiben) und run_eval.py (glob-Suche)
- Roundtrip: Vorlage schreiben → als JSON lesen → Struktur korrekt
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from fibu.cli import (
    _beleg_zu_vorlage_eintrag,
    _eval_ausgabe_pfad,
    _format_betrag_de,
)
from fibu.config import DatenConfig, LokaleConfig
from fibu.contracts import BelegRecord

# ---------------------------------------------------------------------------
# Hilfsfunktion
# ---------------------------------------------------------------------------

def _beleg(**kwargs) -> BelegRecord:
    defaults: dict = {"path": "x.pdf", "rel": "x.pdf", "sha": "abc", "text": "", "alle": []}
    defaults.update(kwargs)
    return BelegRecord(**defaults)


# ---------------------------------------------------------------------------
# _format_betrag_de
# ---------------------------------------------------------------------------

def test_format_tausender() -> None:
    assert _format_betrag_de(Decimal("1234.56")) == "1.234,56"


def test_format_ohne_tausender() -> None:
    assert _format_betrag_de(Decimal("100.00")) == "100,00"


def test_format_millionen() -> None:
    assert _format_betrag_de(Decimal("1000000.50")) == "1.000.000,50"


def test_format_kleine_zahl() -> None:
    assert _format_betrag_de(Decimal("0.99")) == "0,99"


def test_format_quantize_auf_2_stellen() -> None:
    assert _format_betrag_de(Decimal("1234.5")) == "1.234,50"


# ---------------------------------------------------------------------------
# _beleg_zu_vorlage_eintrag
# ---------------------------------------------------------------------------

def test_eintrag_ohne_vorschlag_gold_leer() -> None:
    b = _beleg(alle=[], brutto=[], daten=[], nummern=[])
    e = _beleg_zu_vorlage_eintrag(b, mit_vorschlag=False)
    assert e["betrag"] == ""
    assert e["datum"] == ""
    assert e["nummer"] == ""
    assert "vorschlag" not in e


def test_eintrag_mit_vorschlag_vollstaendig() -> None:
    b = _beleg(
        text="Rechnung\n1234,56",
        alle=[Decimal("1234.56")],
        brutto=[Decimal("1234.56")],
        daten=["15.03.2024"],
        nummern=["2024-001"],
    )
    e = _beleg_zu_vorlage_eintrag(b, mit_vorschlag=True)
    # Gold-Felder bleiben leer
    assert e["betrag"] == ""
    assert e["datum"] == ""
    assert e["nummer"] == ""
    # Vorschlag gefüllt
    assert e["vorschlag"]["betrag"] == "1.234,56"  # type: ignore[index]
    assert e["vorschlag"]["datum"] == "15.03.2024"  # type: ignore[index]
    assert e["vorschlag"]["nummer"] == "2024-001"  # type: ignore[index]


def test_eintrag_mit_vorschlag_nur_nummer() -> None:
    b = _beleg(alle=[], brutto=[], daten=[], nummern=["RG-42"])
    e = _beleg_zu_vorlage_eintrag(b, mit_vorschlag=True)
    assert "datum" not in e.get("vorschlag", {})
    assert e["vorschlag"]["nummer"] == "RG-42"  # type: ignore[index]


def test_eintrag_mit_vorschlag_keine_daten_kein_vorschlag_key() -> None:
    """Kein vorschlag-Schlüssel wenn der Parser nichts gefunden hat."""
    b = _beleg(alle=[], brutto=[], daten=[], nummern=[])
    e = _beleg_zu_vorlage_eintrag(b, mit_vorschlag=True)
    assert "vorschlag" not in e


def test_eintrag_text_gekuerzt() -> None:
    b = _beleg(text="x" * 10000, alle=[])
    e = _beleg_zu_vorlage_eintrag(b, mit_vorschlag=False)
    assert len(e["text"]) == 8000  # type: ignore[arg-type]
    assert len(e["text_snippet"]) == 300  # type: ignore[arg-type]


def test_eintrag_ohne_vorschlag_flag_ignoriert_daten() -> None:
    """Mit mit_vorschlag=False wird vorschlag nie erzeugt."""
    b = _beleg(brutto=[Decimal("500.00")], daten=["01.01.2024"], nummern=["X-1"])
    e = _beleg_zu_vorlage_eintrag(b, mit_vorschlag=False)
    assert "vorschlag" not in e


# ---------------------------------------------------------------------------
# _eval_ausgabe_pfad
# ---------------------------------------------------------------------------

def test_pfad_mit_eval_dir(tmp_path: Path) -> None:
    pfad = _eval_ausgabe_pfad("08 Aug 2024", str(tmp_path), LokaleConfig())
    assert pfad.name == "vorlage_08 Aug 2024.json"
    assert pfad.parent == tmp_path


def test_pfad_mit_wurzel(tmp_path: Path) -> None:
    cfg = LokaleConfig(daten=DatenConfig(wurzel=tmp_path))
    pfad = _eval_ausgabe_pfad("08 Aug 2024", "", cfg)
    assert pfad.name == "vorlage_08 Aug 2024.json"
    assert pfad.parent == tmp_path / "eval"


def test_pfad_fallback_home_wenn_kein_wurzel() -> None:
    cfg = LokaleConfig()  # daten.wurzel ist None
    pfad = _eval_ausgabe_pfad("TestPeriode", "", cfg)
    assert pfad.name == "vorlage_TestPeriode.json"
    # Liegt in ~/.fibu/eval – in jedem Fall außerhalb des Repos
    assert pfad.parent.name == "eval"
    assert pfad.parent.parent.name == ".fibu"


def test_pfad_eval_dir_hat_vorrang_vor_wurzel(tmp_path: Path) -> None:
    eval_dir = tmp_path / "explicit_eval"
    cfg = LokaleConfig(daten=DatenConfig(wurzel=tmp_path / "wurzel"))
    pfad = _eval_ausgabe_pfad("X", str(eval_dir), cfg)
    assert pfad.parent == eval_dir


# ---------------------------------------------------------------------------
# End-to-end: Dateinamen-Konsistenz zwischen Schreiben und Lesen
# ---------------------------------------------------------------------------

def test_dateiname_konsistent_mit_glob(tmp_path: Path) -> None:
    """Datei mit cli-Namensschema geschrieben; glob('vorlage_*.json') findet sie."""
    b = _beleg(text="Betrag: 100,00", alle=[])
    eintrag = _beleg_zu_vorlage_eintrag(b, mit_vorschlag=False)

    period_name = "08 Aug 2024"
    pfad = _eval_ausgabe_pfad(period_name, str(tmp_path), LokaleConfig())
    pfad.write_text(json.dumps([eintrag], indent=2), encoding="utf-8")

    # run_eval.py sucht genau dieses Muster
    dateien = list(tmp_path.glob("vorlage_*.json"))
    assert len(dateien) == 1
    assert dateien[0] == pfad


def test_vorlage_roundtrip(tmp_path: Path) -> None:
    """Schreiben und JSON-Lesen ohne Datenverlust."""
    b = _beleg(
        rel="ordner/rechnung.pdf",
        text="Rechnung 2024-001\n100,00 EUR",
        brutto=[Decimal("100.00")],
        daten=["01.03.2024"],
        nummern=["2024-001"],
        alle=[Decimal("100.00")],
    )
    eintraege = [_beleg_zu_vorlage_eintrag(b, mit_vorschlag=True)]
    pfad = _eval_ausgabe_pfad("TestPeriode", str(tmp_path), LokaleConfig())
    pfad.write_text(json.dumps(eintraege, indent=2, ensure_ascii=False), encoding="utf-8")

    geladen = json.loads(pfad.read_text(encoding="utf-8"))
    assert len(geladen) == 1
    e = geladen[0]
    assert e["beleg"] == "ordner/rechnung.pdf"
    assert e["betrag"] == ""          # Gold-Feld leer
    assert e["vorschlag"]["betrag"] == "100,00"
    assert e["vorschlag"]["datum"] == "01.03.2024"
    assert e["vorschlag"]["nummer"] == "2024-001"


def test_mehrere_vorlagen_glob_findet_letzte(tmp_path: Path) -> None:
    """Wenn mehrere vorlage_*.json existieren, wird die letzte (alphabetisch) geladen."""
    for name in ("vorlage_07 Jul 2024.json", "vorlage_08 Aug 2024.json"):
        (tmp_path / name).write_text("[]", encoding="utf-8")

    dateien = sorted(tmp_path.glob("vorlage_*.json"))
    assert dateien[-1].name == "vorlage_08 Aug 2024.json"
