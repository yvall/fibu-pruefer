from __future__ import annotations

from pathlib import Path

import pytest

from fibu.config import LlmConfig, LokaleConfig

# ---------------------------------------------------------------------------
# LlmConfig-Defaults
# ---------------------------------------------------------------------------

def test_llm_config_defaults() -> None:
    cfg = LlmConfig()
    assert cfg.anbieter == "ollama"
    assert cfg.url == "http://localhost:11434"
    assert cfg.modell == ""
    assert cfg.temperatur == 0.0
    assert cfg.timeout_sekunden == 120
    assert cfg.modell_zuordnung == {}


def test_llm_config_modell_zuordnung() -> None:
    cfg = LlmConfig.model_validate({
        "modell": "mistral:latest",
        "modell_zuordnung": {"beleg-extraktion": "llama3:8b"},
    })
    assert cfg.modell_zuordnung["beleg-extraktion"] == "llama3:8b"
    assert cfg.modell == "mistral:latest"


# ---------------------------------------------------------------------------
# Quell-Auflösung: Env > lokal.yaml > Leer
# ---------------------------------------------------------------------------

def test_env_modell_ueberschreibt_yaml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FIBU_LLM_MODELL", "llama3:latest")
    cfg_datei = tmp_path / "lokal.yaml"
    cfg_datei.write_text("llm:\n  modell: altes-modell\n", encoding="utf-8")
    cfg = LokaleConfig.laden(cfg_datei)
    assert cfg.llm.modell == "llama3:latest"


def test_modell_aus_yaml_ohne_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("FIBU_LLM_MODELL", raising=False)
    cfg_datei = tmp_path / "lokal.yaml"
    cfg_datei.write_text("llm:\n  modell: mistral:latest\n  temperatur: 0.0\n", encoding="utf-8")
    cfg = LokaleConfig.laden(cfg_datei)
    assert cfg.llm.modell == "mistral:latest"
    assert cfg.llm.temperatur == 0.0


def test_fehlendes_modell_ergibt_leerstring(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("FIBU_LLM_MODELL", raising=False)
    cfg_datei = tmp_path / "lokal.yaml"
    cfg_datei.write_text("llm:\n  url: http://localhost:11434\n", encoding="utf-8")
    cfg = LokaleConfig.laden(cfg_datei)
    assert cfg.llm.modell == ""


def test_keine_lokal_yaml_ergibt_leerstring(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("FIBU_LLM_MODELL", raising=False)
    cfg = LokaleConfig.laden(tmp_path / "nicht-vorhanden.yaml")
    assert cfg.llm.modell == ""


def test_env_erhaelt_modell_zuordnung(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """FIBU_LLM_MODELL überschreibt nur das Modell, nicht modell_zuordnung."""
    monkeypatch.setenv("FIBU_LLM_MODELL", "neu:latest")
    cfg_datei = tmp_path / "lokal.yaml"
    cfg_datei.write_text(
        "llm:\n  modell: alt\n  modell_zuordnung:\n    beleg-extraktion: llama3:8b\n",
        encoding="utf-8",
    )
    cfg = LokaleConfig.laden(cfg_datei)
    assert cfg.llm.modell == "neu:latest"
    assert cfg.llm.modell_zuordnung["beleg-extraktion"] == "llama3:8b"


# ---------------------------------------------------------------------------
# LokaleConfig nimmt llm: auf
# ---------------------------------------------------------------------------

def test_lokale_config_hat_llm_feld() -> None:
    cfg = LokaleConfig()
    assert isinstance(cfg.llm, LlmConfig)
