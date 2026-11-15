from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

ZERO = Decimal(0)


class Konto(BaseModel):
    nr: str
    name: str
    eb: Decimal = ZERO
    per_soll: Decimal = ZERO
    per_haben: Decimal = ZERO
    ytd_soll: Decimal = ZERO
    ytd_haben: Decimal = ZERO
    saldo: Decimal = ZERO  # Soll positiv

    @property
    def per_move(self) -> Decimal:
        return self.per_soll - self.per_haben

    @property
    def ytd_move(self) -> Decimal:
        return self.ytd_soll - self.ytd_haben


class WKonto(BaseModel):
    nr: str
    sh: Literal["S", "H"]
    name: str
    per: Decimal = ZERO
    ytd: Decimal = ZERO


class WGroup(BaseModel):
    zeile: str
    name: str
    bwa_per: Decimal | None = None
    bwa_ytd: Decimal | None = None
    kontos: list[WKonto] = Field(default_factory=list)
    ocr: bool = False


class OposItem(BaseModel):
    konto: str
    konto_name: str
    belegnr: str
    datum: str
    faellig: str
    gegenkonto: str
    soll: Decimal = ZERO
    haben: Decimal = ZERO
    text: str = ""


class JahresEintrag(BaseModel):
    datum: str
    text: str
    soll: Decimal = ZERO
    haben: Decimal = ZERO


class JahresKonto(BaseModel):
    nr: str
    name: str
    entries: list[JahresEintrag] = Field(default_factory=list)
    eb: Decimal = ZERO
    saldo: Decimal = ZERO  # Soll positiv
    jvz_soll: Decimal = ZERO
    jvz_haben: Decimal = ZERO


class Rueckfrage(BaseModel):
    datum: str
    betrag: Decimal | None = None
    text: str


class UstvaKz(BaseModel):
    """Ein Kennzeichen der UStVA. base ist None bei reinen Steuerkonten (z. B. Kz. 66)."""

    base: Decimal | None = None
    tax: Decimal | None = None


class Auswertung(BaseModel):
    schema_version: str = "1"
    source: str  # Pfad als String
    year: int = 0
    month: int = 0
    created: str = ""
    # Rohtext je Seite (ersetzt list[pdfwords.Page]; Index 0 = erste Seite)
    page_texts: list[str] = Field(default_factory=list)
    page_types: dict[int, str] = Field(default_factory=dict)
    bwa: dict[str, tuple[Decimal, Decimal]] = Field(default_factory=dict)
    wgroups: list[WGroup] = Field(default_factory=list)
    sus: dict[str, Konto] = Field(default_factory=dict)
    sus_total: dict[str, Decimal] = Field(default_factory=dict)
    opos: list[OposItem] = Field(default_factory=list)
    opos_totals: dict[str, Decimal] = Field(default_factory=dict)
    entwicklung: dict[str, list[Decimal]] = Field(default_factory=dict)
    entw_months: list[str] = Field(default_factory=list)
    ustva: dict[str, UstvaKz] = Field(default_factory=dict)
    ustva_zahllast: Decimal | None = None
    ustva_datum: str = ""
    jahreskonten: list[JahresKonto] = Field(default_factory=list)
    rueckfragen: list[Rueckfrage] = Field(default_factory=list)
    letter_amount: Decimal | None = None
    ocr_pages: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
