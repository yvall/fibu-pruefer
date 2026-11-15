from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class Ref(BaseModel):
    art: Literal["seite", "konto", "beleg"]
    id: str
    label: str = ""


class Calc(BaseModel):
    erwartet: Decimal
    ist: Decimal
    differenz: Decimal
    formel: str = ""


class Finding(BaseModel):
    schema_version: str = "1"
    rule: str
    severity: Literal["fehler", "pruefen", "info"]
    title: str
    detail: str
    calc: Calc | None = None
    refs: list[Ref] = Field(default_factory=list)
