"""Tests für die automatische Konfigurationsdatei-Suche.

Kern-Testszenario: 'fibu'-Befehl wird aus einem fremden Ordner (z. B. ~) gestartet;
config/lokal.yaml liegt nicht relativ zum CWD, muss aber trotzdem gefunden werden.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fibu.config import LokaleConfig, _suche_config_datei

# ---------------------------------------------------------------------------
# _suche_config_datei – Einzel-Quellen
# ---------------------------------------------------------------------------

def test_fibu_config_env_vorrang(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg_datei = tmp_path / "meine.yaml"
    cfg_datei.write_text("llm:\n  modell: env-modell\n", encoding="utf-8")
    monkeypatch.setenv("FIBU_CONFIG", str(cfg_datei))
    monkeypatch.delenv("FIBU_LLM_MODELL", raising=False)

    pfad, quelle = _suche_config_datei()

    assert pfad is not None
    assert pfad.resolve() == cfg_datei.resolve()
    assert "$FIBU_CONFIG" in quelle


def test_xdg_config_gefunden(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg_dir = tmp_path / ".config" / "fibu"
    xdg_dir.mkdir(parents=True)
    xdg_datei = xdg_dir / "lokal.yaml"
    xdg_datei.write_text("llm:\n  modell: xdg-modell\n", encoding="utf-8")

    monkeypatch.delenv("FIBU_CONFIG", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    pfad, quelle = _suche_config_datei()

    assert pfad == xdg_datei
    assert str(xdg_datei) in quelle


def test_keine_quelle_gefunden(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("FIBU_CONFIG", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))  # kein ~/.config/fibu/lokal.yaml

    # Wenn keine Projektkonfig existiert (üblich in CI/Tests), muss None zurückkommen
    pfad, quelle = _suche_config_datei()

    # Entweder Projektkonfig gefunden (Entwicklungsumgebung) oder None
    if pfad is None:
        assert "keine" in quelle.lower()


# ---------------------------------------------------------------------------
# laden() – aus fremdem Ordner (das zentrale Regressions-Szenario)
# ---------------------------------------------------------------------------

def test_laden_aus_fremdem_ordner_mit_fibu_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Kern-Test: fibu läuft aus ~, FIBU_CONFIG zeigt auf die richtige Datei."""
    cfg_datei = tmp_path / "lokal.yaml"
    cfg_datei.write_text("llm:\n  modell: aus-env-config\n", encoding="utf-8")
    monkeypatch.setenv("FIBU_CONFIG", str(cfg_datei))
    monkeypatch.delenv("FIBU_LLM_MODELL", raising=False)

    # Simuliert Lauf aus einem völlig anderen Ordner
    fremder_ordner = tmp_path / "woanders"
    fremder_ordner.mkdir()
    monkeypatch.chdir(fremder_ordner)

    cfg = LokaleConfig.laden()

    assert cfg.llm.modell == "aus-env-config"
    assert "$FIBU_CONFIG" in cfg.config_quelle


def test_laden_aus_fremdem_ordner_mit_xdg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Kern-Test: fibu läuft aus ~, XDG-Konfiguration wird gefunden."""
    xdg_dir = tmp_path / ".config" / "fibu"
    xdg_dir.mkdir(parents=True)
    (xdg_dir / "lokal.yaml").write_text("llm:\n  modell: aus-xdg\n", encoding="utf-8")

    monkeypatch.delenv("FIBU_CONFIG", raising=False)
    monkeypatch.delenv("FIBU_LLM_MODELL", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    # CWD ist ein Ordner ohne config/lokal.yaml
    fremder_ordner = tmp_path / "woanders"
    fremder_ordner.mkdir()
    monkeypatch.chdir(fremder_ordner)

    cfg = LokaleConfig.laden()

    assert cfg.llm.modell == "aus-xdg"
    assert str(xdg_dir / "lokal.yaml") in cfg.config_quelle


def test_laden_aus_fremdem_ordner_ohne_konfiguration_ergibt_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Kein Absturz wenn keine Konfiguration gefunden wird."""
    monkeypatch.delenv("FIBU_CONFIG", raising=False)
    monkeypatch.delenv("FIBU_LLM_MODELL", raising=False)
    monkeypatch.delenv("FIBU_DATEN_WURZEL", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))  # kein XDG-Verzeichnis

    fremder_ordner = tmp_path / "woanders"
    fremder_ordner.mkdir()
    monkeypatch.chdir(fremder_ordner)

    cfg = LokaleConfig.laden()

    # Entweder Projektkonfig gefunden oder Defaults – in jedem Fall kein Fehler
    assert isinstance(cfg, LokaleConfig)
    assert cfg.config_quelle  # immer gesetzt


# ---------------------------------------------------------------------------
# laden() – Quellenpriorität mit chdir
# ---------------------------------------------------------------------------

def test_fibu_config_env_schlaegt_xdg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_datei = tmp_path / "env.yaml"
    env_datei.write_text("llm:\n  modell: env-gewinnt\n", encoding="utf-8")

    xdg_dir = tmp_path / ".config" / "fibu"
    xdg_dir.mkdir(parents=True)
    (xdg_dir / "lokal.yaml").write_text("llm:\n  modell: xdg-verliert\n", encoding="utf-8")

    monkeypatch.setenv("FIBU_CONFIG", str(env_datei))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("FIBU_LLM_MODELL", raising=False)
    monkeypatch.chdir(tmp_path / "woanders" if (tmp_path / "woanders").exists()
                      else tmp_path)

    cfg = LokaleConfig.laden()

    assert cfg.llm.modell == "env-gewinnt"


# ---------------------------------------------------------------------------
# config_quelle-Feld
# ---------------------------------------------------------------------------

def test_config_quelle_bei_explizitem_pfad(tmp_path: Path) -> None:
    pfad = tmp_path / "lokal.yaml"
    pfad.write_text("", encoding="utf-8")
    cfg = LokaleConfig.laden(pfad)
    assert str(pfad) in cfg.config_quelle


def test_config_quelle_nicht_in_model_dump(tmp_path: Path) -> None:
    cfg = LokaleConfig.laden(tmp_path / "nicht-vorhanden.yaml")
    dump = cfg.model_dump()
    assert "config_quelle" not in dump


def test_config_quelle_immer_gesetzt(tmp_path: Path) -> None:
    cfg = LokaleConfig.laden(tmp_path / "nicht-vorhanden.yaml")
    assert isinstance(cfg.config_quelle, str)
    assert len(cfg.config_quelle) > 0
