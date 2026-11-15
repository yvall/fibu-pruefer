"""Prüft, dass 'fibu' von einem beliebigen Arbeitsverzeichnis aus läuft.

Testet explizit den Fall, der ohne korrekte Paketinstallation fehlschlägt:
ModuleNotFoundError: No module named 'legacy'
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_fibu_laeuft_von_fremdem_verzeichnis(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "fibu", "--help"],
        check=False,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Fehler:\n{result.stderr}"
    assert "pruefen" in result.stdout
    assert "monate" in result.stdout
