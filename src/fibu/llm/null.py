"""NullLlmClient: Trockenlauf und Tests – sendet keine Anfragen."""
from __future__ import annotations

from typing import Any


class NullLlmClient:
    """Sendet keine Anfragen. generiere() gibt immer None zurück."""

    @property
    def modell(self) -> str:
        return "null"

    def modell_fuer(self, skill_id: str) -> str:
        return "null"

    def generiere(
        self,
        prompt: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str | None:
        return None
