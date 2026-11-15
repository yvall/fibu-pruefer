from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator


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

    @classmethod
    def laden(cls, config_datei: Path | None = None) -> LokaleConfig:
        """Lädt Konfiguration aus YAML-Datei; FIBU_DATEN_WURZEL überschreibt den Pfad."""
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
        return cls.model_validate(raw)
