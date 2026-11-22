"""NullLlmClient: Trockenlauf und Tests – sendet keine Anfragen."""
from __future__ import annotations

from typing import Any


class NullLlmClient:
    """Sendet keine Anfragen. generiere() gibt immer None zurück."""

    @property
    def modell(self) -> str:
        return "null"

    @property
    def max_befunde_je_gruppe(self) -> int:
        return 3

    def modell_fuer(self, skill_id: str) -> str:
        return "null"

    def generiere(
        self,
        prompt: str,
        json_schema: dict[str, Any] | None = None,
        *,
        modell: str = "",
    ) -> str | None:
        return None
