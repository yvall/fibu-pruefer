from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from fibu.cli import FibuFehler, _monat_aufloesen, _perioden_ordner


def test_perioden_ordner_schliesst_versteckte_aus(tmp_path: Path) -> None:
    (tmp_path / ".versteckt").mkdir()
    (tmp_path / "_intern").mkdir()
    (tmp_path / "08 Aug").mkdir()
    ordner = _perioden_ordner(tmp_path)
    assert [o.name for o in ordner] == ["08 Aug"]


def test_perioden_ordner_schliesst_pruef_im_namen_aus(tmp_path: Path) -> None:
    (tmp_path / "2024-Pruefung").mkdir()
    (tmp_path / "Pruefbericht").mkdir()
    (tmp_path / "08 Aug").mkdir()
    ordner = _perioden_ordner(tmp_path)
    assert [o.name for o in ordner] == ["08 Aug"]


def test_perioden_ordner_ignoriert_dateien(tmp_path: Path) -> None:
    (tmp_path / "08 Aug").mkdir()
    (tmp_path / "liste.txt").write_text("x")
    ordner = _perioden_ordner(tmp_path)
    assert [o.name for o in ordner] == ["08 Aug"]


def test_monat_aufloesen_eindeutig(tmp_path: Path) -> None:
    (tmp_path / "08 Aug 2024").mkdir()
    (tmp_path / "09 Sep 2024").mkdir()
    result = _monat_aufloesen(tmp_path, "08")
    assert result.name == "08 Aug 2024"


def test_monat_aufloesen_voller_name(tmp_path: Path) -> None:
    (tmp_path / "08 Aug 2024").mkdir()
    result = _monat_aufloesen(tmp_path, "08 Aug 2024")
    assert result.name == "08 Aug 2024"


def test_monat_nicht_gefunden(tmp_path: Path) -> None:
    (tmp_path / "09 Sep 2024").mkdir()
    with pytest.raises(FibuFehler, match="nicht gefunden"):
        _monat_aufloesen(tmp_path, "08")


def test_monat_mehrdeutig(tmp_path: Path) -> None:
    (tmp_path / "08 Aug").mkdir()
    (tmp_path / "08b Alt").mkdir()
    with pytest.raises(FibuFehler, match="mehrdeutig"):
        _monat_aufloesen(tmp_path, "08")


def test_monat_leeres_verzeichnis(tmp_path: Path) -> None:
    with pytest.raises(FibuFehler, match="nicht gefunden"):
        _monat_aufloesen(tmp_path, "08")


# ---------------------------------------------------------------------------
# Konfigurationszeile auf stderr
# ---------------------------------------------------------------------------

def test_konfigurationszeile_auf_stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """'Konfiguration: …' erscheint auf stderr, nicht auf stdout."""
    import argparse

    from fibu.cli import _cmd_pruefen
    from fibu.config import LokaleConfig

    ordner = tmp_path / "periode"
    ordner.mkdir()
    cfg = LokaleConfig()
    cfg_quelle = "test-quelle"
    cfg.config_quelle = cfg_quelle  # type: ignore[misc]

    a = argparse.Namespace(ordner=str(ordner), monat=None, llm=False, legacy=False, mail=False)

    with (
        patch("fibu.cli.LokaleConfig.laden", return_value=cfg),
        patch("fibu.cli._cmd_pruefen_skills", return_value=0),
    ):
        _cmd_pruefen(a)

    captured = capsys.readouterr()
    assert "Konfiguration:" not in captured.out
    assert "Konfiguration:" in captured.err
