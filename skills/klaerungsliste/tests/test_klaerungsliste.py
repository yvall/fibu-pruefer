"""Tests für skills/klaerungsliste/check.py."""
from __future__ import annotations

import importlib.util
from decimal import Decimal as D
from pathlib import Path as _P
from typing import Any

_spec = importlib.util.spec_from_file_location("_klaerungsliste", _P(__file__).parent.parent / "check.py")
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run = _mod.run  # type: ignore[attr-defined]

from fibu.contracts import Auswertung, Context, JahresEintrag, JahresKonto, KlaerRow


def _ctx(entries: list[JahresEintrag], rows: list[KlaerRow]) -> Context:
    jk = JahresKonto(nr="1370", name="Verrechnungskonto", eb=D(0),
                     saldo=D(0), jvz_soll=D(0), jvz_haben=D(0), entries=entries)
    return Context(
        auswertung=Auswertung(source="test.pdf", year=2024, month=8, jahreskonten=[jk]),
        klaerung=rows,
    )


def test_keine_klaerung(make_context: Any) -> None:
    ctx = make_context(klaerung=[])
    assert run(ctx) == []


def test_klaerung_in_liste() -> None:
    e = JahresEintrag(datum="01.08.2024", text="Erstattung CA", soll=D(500), haben=D(0))
    row = KlaerRow(text="CA Erstattung August", monat="08/2024", betrag=D(500), kommentar="offen")
    findings = run(_ctx([e], [row]))
    assert any(f.severity == "info" and "in Klärungsliste geführt" in f.title for f in findings)


def test_klaerung_fehlt_in_liste() -> None:
    e = JahresEintrag(datum="01.08.2024", text="Umbuchung Lieferant", soll=D(300), haben=D(0))
    row = KlaerRow(text="Anderer Posten", monat="08/2024", betrag=D(100), kommentar="")
    findings = run(_ctx([e], [row]))
    assert any(f.severity == "pruefen" and "fehlt in der Klärungsliste" in f.title for f in findings)
