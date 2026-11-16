from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class LlmConfig(BaseModel):
    """LLM-Konfiguration. Modell aus FIBU_LLM_MODELL > lokal.yaml > leer (kein LLM).
    Leeres Modell = LLM-Skills erzeugen „nicht verfügbar"-Findings, kein Laufabbruch.
    """
    anbieter: str = "ollama"
    url: str = "http://localhost:11434"
    modell: str = ""   # Leer → LLM-Skills überspringen
    temperatur: float = 0.0
    timeout_sekunden: int = 120
    modell_zuordnung: dict[str, str] = Field(default_factory=dict)


class MailConfig(BaseModel):
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""  # bevorzugt: Umgebungsvariable FIBU_SMTP_PASS
    von: str = ""
    an: list[str] = []  # statische Empfängerliste – nie aus Berichts- oder Beleginhalten


class StoreConfig(BaseModel):
    sqlite_pfad: Path = Path("~/.fibu/laeufe.db")

    @field_validator("sqlite_pfad", mode="before")
    @classmethod
    def _expandiere_tilde(cls, v: object) -> object:
        if isinstance(v, (str, Path)):
            return Path(str(v)).expanduser()
        return v


class DatenConfig(BaseModel):
    wurzel: Path | None = None
    bwa_ordner: str = "BWA"
    bericht_ordner: str = "Pruefbericht"

    @field_validator("wurzel", mode="before")
    @classmethod
    def _expandiere_tilde(cls, v: object) -> object:
        if isinstance(v, (str, Path)):
            return Path(str(v)).expanduser()
        return v


class LokaleConfig(BaseModel):
    daten: DatenConfig = DatenConfig()
    store: StoreConfig = StoreConfig()
    mail: MailConfig = MailConfig()
    llm: LlmConfig = LlmConfig()

    @classmethod
    def laden(cls, config_datei: Path | None = None) -> LokaleConfig:
        """Lädt Konfiguration aus YAML-Datei.

        Umgebungsvariablen überschreiben YAML-Werte:
          FIBU_DATEN_WURZEL → daten.wurzel
          FIBU_LLM_MODELL   → llm.modell
        """
        raw: dict[str, object] = {}
        if config_datei is None:
            config_datei = Path("config/lokal.yaml")
        if config_datei.exists():
            with config_datei.open(encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        env_wurzel = os.environ.get("FIBU_DATEN_WURZEL")
        if env_wurzel:
            daten_raw = raw.get("daten")
            daten: dict[str, object] = dict(daten_raw) if isinstance(daten_raw, dict) else {}
            daten["wurzel"] = env_wurzel
            raw["daten"] = daten
        env_modell = os.environ.get("FIBU_LLM_MODELL")
        if env_modell:
            llm_raw = raw.get("llm")
            llm: dict[str, object] = dict(llm_raw) if isinstance(llm_raw, dict) else {}
            llm["modell"] = env_modell
            raw["llm"] = llm
        return cls.model_validate(raw)
