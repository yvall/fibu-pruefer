"""LlmClient-Protocol: einheitliche Schnittstelle für alle LLM-Backends."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LlmClient(Protocol):
    @property
    def modell(self) -> str:
        """Konfigurierter Modellname (für Logs und Eval-Berichte)."""
        ...

    @property
    def max_befunde_je_gruppe(self) -> int:
        """Maximale Befundanzahl je Gruppe für LLM-Formulierung; darüber → Sammelgruppe."""
        ...

    def modell_fuer(self, skill_id: str) -> str:
        """Gibt das skill-spezifische Modell oder das Standard-Modell zurück."""
        ...

    def generiere(
        self,
        prompt: str,
        json_schema: dict[str, Any] | None = None,
        *,
        modell: str = "",
    ) -> str | None:
        """Schickt einen Prompt an das LLM.

        json_schema: optionales JSON-Schema für Structured Output (Ollama format-Parameter).
        modell: Überschreibt das Standard-Modell für diesen Aufruf (E11 – Skill-spezifisch).
        Gibt None zurück wenn nicht erreichbar, Modell fehlt oder ein Fehler auftritt.
        Der Aufrufer ist für JSON-Parsing (json.loads) zuständig.
        """
        ...
