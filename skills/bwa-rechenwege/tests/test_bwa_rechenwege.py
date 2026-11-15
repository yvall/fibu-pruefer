"""Tests für skills/bwa-rechenwege/check.py."""
from __future__ import annotations

import importlib.util
from decimal import Decimal as D
from pathlib import Path as _P
from typing import Any

_spec = importlib.util.spec_from_file_location("_bwa_rechenwege", _P(__file__).parent.parent / "check.py")
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run = _mod.run  # type: ignore[attr-defined]


def _bwa_korrekt() -> dict[str, Any]:
    """Minimal-BWA mit korrekten Rechenwegen."""
    return {
        "bwa": {
            "Umsatzerlöse":          (D("10000.00"), D("80000.00")),
            "Best.Verdg. FE/UE":     (D("0.00"),     D("0.00")),
            "Akt.Eigenleistungen":   (D("0.00"),     D("0.00")),
            "Gesamtleistung":        (D("10000.00"), D("80000.00")),
            "Mat./Wareneinkauf":     (D("2000.00"),  D("16000.00")),
            "Rohertrag":             (D("8000.00"),  D("64000.00")),
            "So. betr. Erlöse":      (D("0.00"),     D("0.00")),
            "Betriebl. Rohertrag":   (D("8000.00"),  D("64000.00")),
            "Personalkosten":        (D("3000.00"),  D("24000.00")),
            "Raumkosten":            (D("500.00"),   D("4000.00")),
            "Betriebl. Steuern":     (D("0.00"),     D("0.00")),
            "Versich./Beiträge":     (D("100.00"),   D("800.00")),
            "Besondere Kosten":      (D("0.00"),     D("0.00")),
            "Fahrzeugko. (o. St)":   (D("200.00"),   D("1600.00")),
            "Werbe-/Reisekosten":    (D("100.00"),   D("800.00")),
            "Kosten Warenabgabe":    (D("0.00"),     D("0.00")),
            "Abschreibungen":        (D("100.00"),   D("800.00")),
            "Reparatur/Instandh.":   (D("0.00"),     D("0.00")),
            "Sonstige Kosten":       (D("0.00"),     D("0.00")),
            "Gesamtkosten":          (D("4000.00"),  D("32000.00")),
            "Betriebsergebnis":      (D("4000.00"),  D("32000.00")),
            "Zinsaufwand":           (D("0.00"),     D("0.00")),
            "Sonst. neutr. Aufw":    (D("0.00"),     D("0.00")),
            "Neutraler Aufwand":     (D("0.00"),     D("0.00")),
            "Zinserträge":           (D("0.00"),     D("0.00")),
            "Sonst. neutr. Ertr":    (D("0.00"),     D("0.00")),
            "Verr. kalk. Kosten":    (D("0.00"),     D("0.00")),
            "Neutraler Ertrag":      (D("0.00"),     D("0.00")),
            "Kontenkl. unbesetzt":   (D("0.00"),     D("0.00")),
            "Ergebnis vor Steuern":  (D("4000.00"),  D("32000.00")),
            "Steuern Eink.u.Ertr":   (D("0.00"),     D("0.00")),
            "Vorläufiges Ergebnis":  (D("4000.00"),  D("32000.00")),
        }
    }


def test_ohne_befund(make_context: Any) -> None:
    ctx = make_context(**_bwa_korrekt())
    assert run(ctx) == []


def test_mit_befund_vorlaeufigergebnis(make_context: Any) -> None:
    data = _bwa_korrekt()
    # Vorläufiges Ergebnis ist eine Blatt-Zeile ohne Folgewirkung:
    # je ein Befund für Monat und kumuliert, kein Kaskadeneffekt.
    bwa = dict(data["bwa"])
    bwa["Vorläufiges Ergebnis"] = (D("4010.00"), D("32010.00"))
    data["bwa"] = bwa
    ctx = make_context(**data)
    findings = run(ctx)
    fehler = [f for f in findings if f.severity == "fehler"]
    assert len(fehler) == 2
    assert all("Vorläufiges Ergebnis" in f.title for f in fehler)
    assert all(f.rule == "bwa-rechenwege" for f in fehler)
    assert all(f.calc is not None for f in fehler)


def test_toleranz_exakt(make_context: Any) -> None:
    data = _bwa_korrekt()
    # Differenz genau 0,02 € → kein Befund (Grenzwert inklusiv)
    bwa = dict(data["bwa"])
    bwa["Gesamtleistung"] = (D("10000.02"), D("80000.00"))
    data["bwa"] = bwa
    ctx = make_context(**data)
    assert run(ctx) == []


def test_bwa_nicht_lesbar(make_context: Any) -> None:
    ctx = make_context(bwa={})
    findings = run(ctx)
    assert len(findings) == 1
    assert findings[0].title == "BWA nicht lesbar"
    assert findings[0].severity == "fehler"
    assert findings[0].rule == "bwa-rechenwege"
