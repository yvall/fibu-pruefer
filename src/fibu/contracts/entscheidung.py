from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Entscheidung(BaseModel):
    schema_version: str = "1"
    freigabe: Literal["freigegeben", "gesperrt", "ausstehend"] = "ausstehend"
    freigegeben_von: str = ""
    freigegeben_am: datetime | None = None
    kommentar: str = ""
