from __future__ import annotations

from pathlib import Path

import pytest

from fibu.config import LokaleConfig


def test_keine_config_ergibt_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIBU_DATEN_WURZEL", raising=False)
    config = LokaleConfig.laden(tmp_path / "nicht_vorhanden.yaml")
    assert config.daten.wurzel is None
    assert config.daten.bwa_ordner == "BWA"
    assert config.daten.bericht_ordner == "Pruefbericht"


def test_laden_aus_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIBU_DATEN_WURZEL", raising=False)
    yaml_file = tmp_path / "lokal.yaml"
    yaml_file.write_text(
        f"daten:\n  wurzel: {tmp_path}\n  bwa_ordner: Belege\n", encoding="utf-8"
    )
    config = LokaleConfig.laden(yaml_file)
    assert config.daten.wurzel == tmp_path
    assert config.daten.bwa_ordner == "Belege"


def test_laden_aus_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIBU_DATEN_WURZEL", str(tmp_path))
    config = LokaleConfig.laden(tmp_path / "nicht_vorhanden.yaml")
    assert config.daten.wurzel == tmp_path


def test_env_ueberschreibt_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_file = tmp_path / "lokal.yaml"
    yaml_file.write_text("daten:\n  wurzel: /alt\n", encoding="utf-8")
    monkeypatch.setenv("FIBU_DATEN_WURZEL", str(tmp_path))
    config = LokaleConfig.laden(yaml_file)
    assert config.daten.wurzel == tmp_path


def test_tilde_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIBU_DATEN_WURZEL", raising=False)
    yaml_file = tmp_path / "lokal.yaml"
    yaml_file.write_text("daten:\n  wurzel: ~/irgendwas\n", encoding="utf-8")
    config = LokaleConfig.laden(yaml_file)
    assert config.daten.wurzel is not None
    assert "~" not in str(config.daten.wurzel)
    assert config.daten.wurzel.is_absolute()


def test_env_tilde_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIBU_DATEN_WURZEL", "~/irgendwas")
    config = LokaleConfig.laden(tmp_path / "nicht_vorhanden.yaml")
    assert config.daten.wurzel is not None
    assert "~" not in str(config.daten.wurzel)
    assert config.daten.wurzel.is_absolute()
