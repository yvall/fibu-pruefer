from decimal import Decimal

import pytest
from pydantic import ValidationError

from fibu.contracts import Auswertung, Konto, OposItem, WGroup, WKonto
from fibu.contracts.auswertung import JahresEintrag, JahresKonto, Rueckfrage, UstvaKz


def test_konto_per_move():
    k = Konto(nr="4000", name="Umsatz", per_soll=Decimal("100"), per_haben=Decimal("80"))
    assert k.per_move == Decimal("20")


def test_konto_ytd_move():
    k = Konto(nr="4000", name="Umsatz", ytd_soll=Decimal("800"), ytd_haben=Decimal("600"))
    assert k.ytd_move == Decimal("200")


def test_konto_defaults():
    k = Konto(nr="1200", name="Debitoren")
    assert k.eb == Decimal("0")
    assert k.saldo == Decimal("0")


def test_wgroup_validation():
    wg = WGroup(
        zeile="1051",
        name="Gesamtleistung",
        bwa_per=Decimal("10000"),
        kontos=[WKonto(nr="4000", sh="H", name="Umsatz", per=Decimal("10000"), ytd=Decimal("80000"))],
    )
    assert wg.kontos[0].sh == "H"
    assert wg.bwa_per == Decimal("10000")


def test_wkonto_invalid_sh():
    with pytest.raises(ValidationError):
        WKonto(nr="4000", sh="X", name="Umsatz")  # type: ignore[arg-type]


def test_auswertung_minimal():
    a = Auswertung(source="bericht.pdf", year=2024, month=8)
    assert a.year == 2024
    assert a.month == 8
    assert a.bwa == {}
    assert a.sus == {}
    assert a.wgroups == []
    assert a.schema_version == "1"


def test_auswertung_with_bwa():
    a = Auswertung(
        source="bericht.pdf",
        year=2024,
        month=8,
        bwa={"Umsatzerlöse": (Decimal("10000.00"), Decimal("80000.00"))},
    )
    monat, kum = a.bwa["Umsatzerlöse"]
    assert monat == Decimal("10000.00")
    assert kum == Decimal("80000.00")


def test_auswertung_json_roundtrip_basic():
    a = Auswertung(
        source="test.pdf",
        year=2024,
        month=8,
        bwa={"Umsatz": (Decimal("1234.56"), Decimal("9876.54"))},
        sus={"4000": Konto(nr="4000", name="Umsatz", per_haben=Decimal("1234.56"))},
    )
    json_str = a.model_dump_json()
    a2 = Auswertung.model_validate_json(json_str)
    assert a2.bwa["Umsatz"] == (Decimal("1234.56"), Decimal("9876.54"))
    assert isinstance(a2.bwa["Umsatz"][0], Decimal)
    assert a2.sus["4000"].per_haben == Decimal("1234.56")


def test_auswertung_page_types_int_keys_roundtrip():
    a = Auswertung(source="x.pdf", year=2024, month=1, page_types={1: "bwa", 3: "sus"})
    json_str = a.model_dump_json()
    a2 = Auswertung.model_validate_json(json_str)
    assert a2.page_types[1] == "bwa"
    assert a2.page_types[3] == "sus"
    assert all(isinstance(k, int) for k in a2.page_types)


def test_auswertung_decimal_precision():
    a = Auswertung(
        source="x.pdf",
        year=2024,
        month=1,
        sus={"3806": Konto(nr="3806", name="USt 19%", saldo=Decimal("-123.45"))},
    )
    json_str = a.model_dump_json()
    a2 = Auswertung.model_validate_json(json_str)
    assert a2.sus["3806"].saldo == Decimal("-123.45")


def test_ustva_kz():
    kz = UstvaKz(base=Decimal("1000.00"), tax=Decimal("190.00"))
    assert kz.base == Decimal("1000.00")
    assert kz.tax == Decimal("190.00")


def test_ustva_kz_none():
    kz = UstvaKz()
    assert kz.base is None
    assert kz.tax is None


def test_auswertung_with_ustva():
    a = Auswertung(
        source="x.pdf",
        year=2024,
        month=8,
        ustva={
            "81": UstvaKz(base=Decimal("10000"), tax=Decimal("1900")),
            "66": UstvaKz(tax=Decimal("500")),
            "83": UstvaKz(tax=Decimal("1400")),
        },
    )
    json_str = a.model_dump_json()
    a2 = Auswertung.model_validate_json(json_str)
    assert a2.ustva["81"].tax == Decimal("1900")
    assert a2.ustva["66"].base is None
    assert a2.ustva["83"].tax == Decimal("1400")


def test_jahreskonten_roundtrip():
    a = Auswertung(
        source="x.pdf",
        year=2024,
        month=8,
        jahreskonten=[
            JahresKonto(
                nr="1370",
                name="Durchlaufende Posten",
                entries=[JahresEintrag(datum="01.08.2024", text="Erstattung", soll=Decimal("500"))],
                saldo=Decimal("500"),
            )
        ],
    )
    json_str = a.model_dump_json()
    a2 = Auswertung.model_validate_json(json_str)
    assert a2.jahreskonten[0].nr == "1370"
    assert a2.jahreskonten[0].entries[0].soll == Decimal("500")


def test_opos_item():
    item = OposItem(
        konto="10001",
        konto_name="Muster GmbH",
        belegnr="RE-2024-001",
        datum="15.08.2024",
        faellig="14.09.2024",
        gegenkonto="4000",
        soll=Decimal("1190.00"),
    )
    assert item.soll == Decimal("1190.00")
    assert item.haben == Decimal("0")


def test_rueckfrage_optional_betrag():
    r = Rueckfrage(datum="01.08.2024", text="Klärung erforderlich")
    assert r.betrag is None
    r2 = Rueckfrage(datum="01.08.2024", betrag=Decimal("500.00"), text="Erstattung prüfen")
    assert r2.betrag == Decimal("500.00")
