"""Tests für skills/vormonat-fortschreibung/check.py."""
from __future__ import annotations

import importlib.util
from decimal import Decimal as D
from pathlib import Path as _P
from typing import Any

_spec = importlib.util.spec_from_file_location("_vormonat_fortschreibung", _P(__file__).parent.parent / "check.py")
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run = _mod.run  # type: ignore[attr-defined]

from fibu.contracts import Auswertung, Context, Konto


def _a(**kw: Any) -> Auswertung:
    defaults: dict[str, Any] = {"source": "test.pdf", "year": 2024, "month": 8}
    defaults.update(kw)
    return Auswertung(**defaults)


def _ctx(a: Auswertung, p: Auswertung | None = None) -> Context:
    return Context(auswertung=a, prev=p)


def test_ohne_prev() -> None:
    ctx = _ctx(_a())
    findings = run(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert "Keine Vormonats-BWA" in findings[0].title


def test_falscher_vormonat() -> None:
    # a=August, p=Juni → nicht unmittelbar vorhergehend
    ctx = _ctx(_a(month=8, year=2024), _a(month=6, year=2024))
    findings = run(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert "nicht unmittelbar" in findings[0].title


def test_bwa_fortschreibung_ok() -> None:
    # kum. prev(1000) + per(500) = kum. aktuell(1500) ✓
    ctx = _ctx(
        _a(month=8, year=2024,
           bwa={"Umsatzerlöse": (D(500), D(1500))}),
        _a(month=7, year=2024,
           bwa={"Umsatzerlöse": (D(0), D(1000))}),
    )
    assert run(ctx) == []


def test_bwa_fortschreibung_abweichung() -> None:
    # kum. prev(1000) + per(500) = 1500, aber ausgewiesen 1600 → Rückwirkungsbuchung
    ctx = _ctx(
        _a(month=8, year=2024,
           bwa={"Umsatzerlöse": (D(500), D(1600))}),
        _a(month=7, year=2024,
           bwa={"Umsatzerlöse": (D(0), D(1000))}),
    )
    findings = run(ctx)
    assert any(f.severity == "fehler" and "kum. Vormonat" in f.title for f in findings)


def test_konto_geaendert() -> None:
    # Konto 4000 hatte im Vormonat ytd_soll=1000, jetzt hat es ytd_soll-per_soll=1200 → Differenz 200
    k_aktuell = Konto(nr="4000", name="Umsatz", eb=D(0),
                      per_soll=D(0), per_haben=D(500),
                      ytd_soll=D(0), ytd_haben=D(1200), saldo=D(-1200))
    k_vormonat = Konto(nr="4000", name="Umsatz", eb=D(0),
                       per_soll=D(0), per_haben=D(0),
                       ytd_soll=D(0), ytd_haben=D(1000), saldo=D(-1000))
    ctx = _ctx(
        _a(month=8, year=2024, sus={"4000": k_aktuell}),
        _a(month=7, year=2024, sus={"4000": k_vormonat}),
    )
    findings = run(ctx)
    assert any(f.severity == "pruefen" and "Konten mit nachträglich" in f.title for f in findings)


def test_meta_changed_exportiert() -> None:
    k_aktuell = Konto(nr="4000", name="X", eb=D(0),
                      per_soll=D(0), per_haben=D(500),
                      ytd_soll=D(0), ytd_haben=D(1200), saldo=D(-1200))
    k_vormonat = Konto(nr="4000", name="X", eb=D(0),
                       per_soll=D(0), per_haben=D(0),
                       ytd_soll=D(0), ytd_haben=D(1000), saldo=D(-1000))
    ctx = _ctx(
        _a(month=8, year=2024, sus={"4000": k_aktuell}),
        _a(month=7, year=2024, sus={"4000": k_vormonat}),
    )
    run(ctx)
    assert isinstance(_mod._meta.get("changed"), list)
    assert len(_mod._meta["changed"]) > 0
