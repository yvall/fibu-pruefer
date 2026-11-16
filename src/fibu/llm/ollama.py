"""OllamaClient: LLM-Backend für lokales Ollama (kein Pip-Paket nötig)."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from fibu.config import LlmConfig

log = logging.getLogger(__name__)


class OllamaClient:
    """Spricht mit der Ollama-API über /api/generate.

    Temperatur 0.0 und Modellname kommen aus LlmConfig.
    generiere() gibt None zurück bei Fehler, Netz-Ausfall oder fehlendem Modell.
    """

    def __init__(self, config: LlmConfig) -> None:
        self._config = config

    @classmethod
    def aus_config(cls, config: LlmConfig) -> OllamaClient:
        return cls(config)

    # ------------------------------------------------------------------
    # Protocol-Methoden
    # ------------------------------------------------------------------

    @property
    def modell(self) -> str:
        return self._config.modell

    def modell_fuer(self, skill_id: str) -> str:
        """Gibt das skill-spezifische Modell aus modell_zuordnung oder das Standard-Modell."""
        return self._config.modell_zuordnung.get(skill_id, self._config.modell)

    def generiere(
        self,
        prompt: str,
        json_schema: dict[str, Any] | None = None,
    ) -> str | None:
        """Schickt prompt an /api/generate. Gibt den Response-String oder None zurück.

        json_schema: Wenn angegeben, wird er als 'format'-Parameter mitgeschickt
        (Ollama Structured Output). Ob das Modell ihn unterstützt, prüft 'fibu llm pruefen'.
        JSON-Parsing ist Aufgabe des Aufrufers.
        """
        if not self._config.modell:
            log.debug("Kein LLM-Modell konfiguriert – Aufruf übersprungen")
            return None

        body: dict[str, Any] = {
            "model": self._config.modell,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self._config.temperatur},
        }
        if json_schema is not None:
            body["format"] = json_schema

        encoded = json.dumps(body, ensure_ascii=False).encode()
        req = urllib.request.Request(
            f"{self._config.url.rstrip('/')}/api/generate",
            encoded,
            {"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._config.timeout_sekunden) as r:
                data = json.loads(r.read())
                return str(data["response"]).strip()
        except urllib.error.HTTPError as exc:
            fehler_body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404 or "not found" in fehler_body.lower():
                log.warning(
                    "Modell '%s' nicht installiert – installieren mit: ollama pull %s",
                    self._config.modell,
                    self._config.modell,
                )
            else:
                log.warning("Ollama HTTP %d: %s", exc.code, fehler_body[:200])
            return None
        except Exception as exc:  # noqa: BLE001 – Netzwerk/Timeout/JSON: immer None
            log.warning("Ollama nicht erreichbar: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Diagnose (für 'fibu llm pruefen')
    # ------------------------------------------------------------------

    def ist_verfuegbar(self) -> tuple[bool, str]:
        """Prüft Ollama-Erreichbarkeit und ob das konfigurierte Modell installiert ist.

        Gibt (True, Versionsinfo) oder (False, deutsche Fehlermeldung) zurück.
        """
        base = self._config.url.rstrip("/")

        # 1. Erreichbarkeit
        try:
            req = urllib.request.Request(f"{base}/api/version")
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read())
            version = str(data.get("version", "unbekannt"))
        except Exception as exc:  # noqa: BLE001 – Netzwerk/Timeout: nicht erreichbar
            return False, f"Ollama nicht erreichbar ({exc})"

        if not self._config.modell:
            return False, "Kein Modell konfiguriert (llm.modell in lokal.yaml oder FIBU_LLM_MODELL)"

        # 2. Modell installiert?
        try:
            req = urllib.request.Request(f"{base}/api/tags")
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            installiert = [m["name"] for m in data.get("models", [])]
            # Normalize: "mistral" → "mistral:latest" für Vergleich
            modell = self._config.modell
            modell_norm = modell if ":" in modell else f"{modell}:latest"
            if modell not in installiert and modell_norm not in installiert:
                return (
                    False,
                    f"Modell '{modell}' nicht installiert – installieren mit: ollama pull {modell}",
                )
        except Exception as exc:  # noqa: BLE001 – /api/tags nicht erreichbar
            return False, f"Modell-Prüfung fehlgeschlagen: {exc}"

        return True, f"Ollama {version}"

    def pruefe_structured_output(self) -> bool:
        """Sendet einen kleinen Test mit JSON-Schema und prüft ob das Modell antwortet.

        Gibt True zurück wenn das Modell gültiges JSON mit dem erwarteten Schlüssel liefert.
        """
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {"ergebnis": {"type": "string"}},
            "required": ["ergebnis"],
            "additionalProperties": False,
        }
        antwort = self.generiere(
            'Antworte ausschließlich mit einem JSON-Objekt mit dem Schlüssel "ergebnis" '
            'und dem Wert "ok".',
            json_schema=schema,
        )
        if not antwort:
            return False
        try:
            parsed = json.loads(antwort)
            return isinstance(parsed, dict) and "ergebnis" in parsed
        except json.JSONDecodeError:
            return False
