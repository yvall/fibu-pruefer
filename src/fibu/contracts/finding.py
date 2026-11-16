from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class Ref(BaseModel):
    art: Literal["seite", "konto", "beleg"]
    id: str
    label: str = ""


class Calc(BaseModel):
    erwartet: Decimal
    ist: Decimal
    differenz: Decimal
    formel: str = ""


def _ohne_zahlen(text: str) -> str:
    """Entfernt Ziffernfolgen und Beträge; macht den Text mengenunabhängig."""
    bereinigt = re.sub(r"\d[\d.,]*", "", text)
    return re.sub(r"\s+", " ", bereinigt).strip()


class Finding(BaseModel):
    schema_version: str = "2"
    rule: str
    severity: Literal["fehler", "pruefen", "info"]
    title: str
    detail: str
    calc: Calc | None = None
    refs: list[Ref] = Field(default_factory=list)
    id_suffix: str = ""  # von Runtime gesetzt bei ID-Kollision (z. B. "#2")

    def _fachlicher_schluessel(self) -> str:
        """Betrag-unabhängiger Schlüssel für die Finding-ID."""
        if self.refs:
            return "|".join(sorted(f"{r.art}/{r.id}" for r in self.refs))
        if self.calc and self.calc.formel:
            return _ohne_zahlen(self.calc.formel)[:80]
        # Titel: Zahlen entfernen, auf Kleinbuchstaben und Trennzeichen reduzieren
        normiert = re.sub(r"[^a-z_ ]", "", _ohne_zahlen(self.title).lower())
        return normiert[:60]

    @computed_field  # type: ignore[misc]
    @property
    def id(self) -> str:
        """Stabile ID: sha256({rule}:{fachlicher_schluessel})[:16] + optionales Suffix."""
        raw = f"{self.rule}:{self._fachlicher_schluessel()}"
        basis = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{basis}{self.id_suffix}" if self.id_suffix else basis
