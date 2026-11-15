from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from .auswertung import Auswertung
from .beleg import BelegRecord

# (kontonr, name, Δsoll, Δhaben) – Ergebnis von vormonat-fortschreibung
ChangedKonto = tuple[str, str, Decimal, Decimal]


class KlaerRow(BaseModel):
    text: str
    monat: str
    betrag: Decimal | None = None
    kommentar: str = ""


class Context(BaseModel):
    auswertung: Auswertung
    prev: Auswertung | None = None
    belege: list[BelegRecord] = Field(default_factory=list)
    klaerung: list[KlaerRow] = Field(default_factory=list)
    # Befüllt durch die Runtime nach Ausführung von vormonat-fortschreibung
    changed_accounts: list[tuple[str, str, Decimal, Decimal]] = Field(default_factory=list)
    config: dict[str, object] = Field(default_factory=dict)
