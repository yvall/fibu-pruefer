from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class LaufInfo:
    lauf_id: str
    ordner: str
    gestartet: datetime
    geschlossen: datetime | None
    status: str  # "laufend" | "wartend" | "abgeschlossen" | "fehler"
