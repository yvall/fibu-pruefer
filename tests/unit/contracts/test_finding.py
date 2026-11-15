from decimal import Decimal

import pytest
from pydantic import ValidationError

from fibu.contracts import Calc, Finding, Ref


def test_finding_minimal():
    f = Finding(rule="bwa-rechenwege", severity="fehler", title="Titel", detail="Detail")
    assert f.rule == "bwa-rechenwege"
    assert f.refs == []
    assert f.calc is None


def test_finding_with_calc_and_refs():
    f = Finding(
        rule="bwa-rechenwege",
        severity="fehler",
        title="BWA stimmt nicht",
        detail="Differenz 1,00 €",
        calc=Calc(
            erwartet=Decimal("100.00"),
            ist=Decimal("99.00"),
            differenz=Decimal("1.00"),
            formel="Umsatz + Kosten",
        ),
        refs=[Ref(art="konto", id="4000", label="Umsatzerlöse")],
    )
    assert f.calc is not None
    assert f.calc.differenz == Decimal("1.00")
    assert f.refs[0].art == "konto"
    assert f.refs[0].id == "4000"


def test_finding_severity_values():
    for sev in ("fehler", "pruefen", "info"):
        f = Finding(rule="x", severity=sev, title="T", detail="D")
        assert f.severity == sev


def test_finding_invalid_severity():
    with pytest.raises(ValidationError):
        Finding(rule="x", severity="ungueltig", title="T", detail="D")


def test_finding_json_roundtrip():
    f = Finding(
        rule="ustva-abgleich",
        severity="pruefen",
        title="Kz. 81 abweichend",
        detail="UStVA 1.000,00 € ≠ Konten 999,00 €",
        calc=Calc(
            erwartet=Decimal("1000.00"),
            ist=Decimal("999.00"),
            differenz=Decimal("1.00"),
            formel="Konten 44xx",
        ),
        refs=[Ref(art="konto", id="3806")],
    )
    json_str = f.model_dump_json()
    f2 = Finding.model_validate_json(json_str)
    assert f2 == f
    assert isinstance(f2.calc.erwartet, Decimal)  # type: ignore[union-attr]


def test_ref_arten():
    for art in ("seite", "konto", "beleg"):
        r = Ref(art=art, id="1")
        assert r.art == art


def test_ref_invalid_art():
    with pytest.raises(ValidationError):
        Ref(art="unbekannt", id="1")  # type: ignore[arg-type]
