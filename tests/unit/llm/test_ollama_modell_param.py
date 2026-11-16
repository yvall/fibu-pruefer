"""Tests für den optionalen modell-Parameter in OllamaClient.generiere() (E11)."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from fibu.config import LlmConfig
from fibu.llm.ollama import OllamaClient


def _config(**kwargs: Any) -> LlmConfig:
    defaults: dict[str, Any] = {"modell": "mistral:latest"}
    defaults.update(kwargs)
    return LlmConfig.model_validate(defaults)


def _mock_response(data: dict[str, Any]) -> MagicMock:
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = json.dumps(data).encode()
    return mock


def _capture_body(response_data: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    """Hilfsfunktion: fängt den Request-Body ab und gibt (captured, mock_fn) zurück."""
    captured: dict[str, Any] = {}

    def mock_open(req: Any, timeout: int = 0) -> Any:
        captured.update(json.loads(req.data))
        return _mock_response(response_data)

    return captured, mock_open


def test_generiere_modell_param_setzt_model_key() -> None:
    """modell='llama3' setzt body['model'] = 'llama3', nicht den Config-Wert."""
    client = OllamaClient.aus_config(_config(modell="mistral:latest"))
    captured, mock_open = _capture_body({"response": "ok"})

    with patch("urllib.request.urlopen", side_effect=mock_open):
        client.generiere("Test", modell="llama3")

    assert captured["model"] == "llama3"


def test_generiere_leerer_modell_param_nutzt_config() -> None:
    """modell='' (default) → body['model'] kommt aus self._config.modell."""
    client = OllamaClient.aus_config(_config(modell="mistral:latest"))
    captured, mock_open = _capture_body({"response": "ok"})

    with patch("urllib.request.urlopen", side_effect=mock_open):
        client.generiere("Test")  # kein modell-Argument

    assert captured["model"] == "mistral:latest"


def test_generiere_modell_param_bei_leerem_config_macht_request() -> None:
    """Config-Modell leer, aber modell-Parameter gesetzt → Request wird gemacht."""
    client = OllamaClient.aus_config(_config(modell=""))
    captured, mock_open = _capture_body({"response": "ok"})

    with patch("urllib.request.urlopen", side_effect=mock_open):
        result = client.generiere("Test", modell="llama3")

    assert result == "ok"
    assert captured["model"] == "llama3"


def test_generiere_modell_param_und_config_beide_leer_gibt_none() -> None:
    """Config-Modell leer + kein modell-Parameter → None (kein Request)."""
    client = OllamaClient.aus_config(_config(modell=""))
    with patch("urllib.request.urlopen") as mock_open:
        result = client.generiere("Test")
    mock_open.assert_not_called()
    assert result is None
