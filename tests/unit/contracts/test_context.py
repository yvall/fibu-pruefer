from decimal import Decimal

from fibu.contracts import Auswertung, BelegRecord, Context, KlaerRow
from fibu.contracts.context import ChangedKonto


def _auswertung() -> Auswertung:
    return Auswertung(source="x.pdf", year=2024, month=8)


def test_context_minimal():
    ctx = Context(auswertung=_auswertung())
    assert ctx.prev is None
    assert ctx.belege == []
    assert ctx.klaerung == []
    assert ctx.changed_accounts == []
    assert ctx.config == {}


def test_context_with_prev():
    ctx = Context(auswertung=_auswertung(), prev=Auswertung(source="x.pdf", year=2024, month=7))
    assert ctx.prev is not None
    assert ctx.prev.month == 7


def test_context_with_changed_accounts():
    changed: list[ChangedKonto] = [
        ("4000", "Umsatzerlöse", Decimal("100.00"), Decimal("0.00")),
        ("3806", "USt 19%", Decimal("0.00"), Decimal("19.00")),
    ]
    ctx = Context(auswertung=_auswertung(), changed_accounts=changed)
    assert len(ctx.changed_accounts) == 2
    assert ctx.changed_accounts[0][0] == "4000"
    assert ctx.changed_accounts[1][2] == Decimal("0.00")


def test_context_with_belege():
    b = BelegRecord(path="/tmp/rechnung.pdf", rel="CA/rechnung.pdf", sha="abc123")
    ctx = Context(auswertung=_auswertung(), belege=[b])
    assert ctx.belege[0].sha == "abc123"


def test_klaerrow_with_betrag():
    row = KlaerRow(text="Erstattung Muster", monat="08/2024", betrag=Decimal("123.45"), kommentar="OK")
    assert row.betrag == Decimal("123.45")
    assert row.monat == "08/2024"


def test_klaerrow_betrag_optional():
    row = KlaerRow(text="Ohne Betrag", monat="08/2024")
    assert row.betrag is None
    assert row.kommentar == ""


def test_beleg_record_primary():
    b = BelegRecord(
        path="/tmp/r.pdf",
        rel="r.pdf",
        sha="abc",
        brutto=[Decimal("119.00"), Decimal("238.00")],
    )
    assert b.primary == Decimal("238.00")


def test_beleg_record_primary_empty():
    b = BelegRecord(path="/tmp/r.pdf", rel="r.pdf", sha="abc")
    assert b.primary is None


def test_context_json_roundtrip():
    ctx = Context(
        auswertung=Auswertung(
            source="x.pdf",
            year=2024,
            month=8,
            bwa={"Umsatz": (Decimal(1000), Decimal(8000))},
        ),
        klaerung=[KlaerRow(text="Test", monat="08/2024", betrag=Decimal(100))],
        changed_accounts=[("4000", "Umsatz", Decimal(100), Decimal(0))],
    )
    json_str = ctx.model_dump_json()
    ctx2 = Context.model_validate_json(json_str)
    assert ctx2.auswertung.bwa["Umsatz"] == (Decimal(1000), Decimal(8000))
    assert ctx2.klaerung[0].betrag == Decimal(100)
    assert ctx2.changed_accounts[0][0] == "4000"
    assert isinstance(ctx2.changed_accounts[0][2], Decimal)
