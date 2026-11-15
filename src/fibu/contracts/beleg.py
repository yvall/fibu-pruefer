from __future__ import annotations

import re
from decimal import Decimal

from pydantic import BaseModel, Field


class BelegRecord(BaseModel):
    schema_version: str = "1"
    path: str
    rel: str
    sha: str
    text: str = ""
    kind: str = "beleg"  # rechnung | gutschrift | beleg | eigenbeleg | storno
    brutto: list[Decimal] = Field(default_factory=list)
    netto: list[Decimal] = Field(default_factory=list)
    alle: list[Decimal] = Field(default_factory=list)
    daten: list[str] = Field(default_factory=list)
    nummern: list[str] = Field(default_factory=list)
    leistung: tuple[int, int] | None = None
    ocr: bool = False

    @property
    def norm(self) -> str:
        return re.sub(r"[\s\-/]", "", self.text).upper().replace("O", "0")

    @property
    def primary(self) -> Decimal | None:
        return max(self.brutto) if self.brutto else None
