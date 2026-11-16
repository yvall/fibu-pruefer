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


def _suche_config_datei() -> tuple[Path | None, str]:
    """Sucht die Konfigurationsdatei unabhängig vom Arbeitsverzeichnis.

    Reihenfolge:
    1. FIBU_CONFIG – voller Pfad zur Datei
    2. ~/.config/fibu/lokal.yaml
    3. config/lokal.yaml relativ zum Paketverzeichnis (nicht zum CWD)
    """
    # 1. Umgebungsvariable FIBU_CONFIG
    env_config = os.environ.get("FIBU_CONFIG")
    if env_config:
        p = Path(env_config).expanduser().resolve()
        return p, f"$FIBU_CONFIG → {p}"

    # 2. XDG-Standard: ~/.config/fibu/lokal.yaml
    xdg = Path.home() / ".config" / "fibu" / "lokal.yaml"
    if xdg.exists():
        return xdg, str(xdg)

    # 3. Projektordner relativ zum Paket – unabhängig vom aktuellen Arbeitsverzeichnis
    projekt = Path(__file__).resolve().parent.parent.parent / "config" / "lokal.yaml"
    if projekt.exists():
        return projekt, str(projekt)

    return None, "(keine Konfigurationsdatei gefunden)"


class LokaleConfig(BaseModel):
    daten: DatenConfig = DatenConfig()
    store: StoreConfig = StoreConfig()
    mail: MailConfig = MailConfig()
    llm: LlmConfig = LlmConfig()
    config_quelle: str = Field(
        default="(keine Konfigurationsdatei gefunden)",
        exclude=True,  # nicht in model_dump() – reine Laufzeit-Metadaten
    )

    @classmethod
    def laden(cls, config_datei: Path | None = None) -> LokaleConfig:
        """Lädt Konfiguration; zeigt über config_quelle, welche Datei verwendet wurde.

        config_datei=None: Auto-Suche (FIBU_CONFIG → XDG → Projektordner).
        config_datei=Pfad: Explizite Angabe (für Tests und interne Aufrufe).

        Umgebungsvariablen überschreiben YAML-Werte:
          FIBU_DATEN_WURZEL → daten.wurzel
          FIBU_LLM_MODELL   → llm.modell
        """
        if config_datei is not None:
            pfad: Path | None = config_datei
            quelle = str(config_datei)
        else:
            pfad, quelle = _suche_config_datei()

        raw: dict[str, object] = {}
        if pfad is not None and pfad.exists():
            with pfad.open(encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}

        # Umgebungsvariablen-Overrides
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

        raw["config_quelle"] = quelle
        return cls.model_validate(raw)
