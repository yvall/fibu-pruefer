from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

from fibu.config import LlmConfig
from fibu.llm.ollama import OllamaClient
from fibu.llm.protocol import LlmClient


def _config(**kwargs: Any) -> LlmConfig:
    defaults: dict[str, Any] = {"modell": "mistral:latest"}
    defaults.update(kwargs)
    return LlmConfig.model_validate(defaults)


def _mock_response(data: dict[str, Any]) -> MagicMock:
    """Erstellt ein urllib-Response-Mock für json.loads(r.read())."""
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = json.dumps(data).encode()
    return mock


# ---------------------------------------------------------------------------
# Protocol-Konformität
# ---------------------------------------------------------------------------

def test_ollama_client_implementiert_protocol() -> None:
    client = OllamaClient.aus_config(_config())
    assert isinstance(client, LlmClient)


# ---------------------------------------------------------------------------
# modell / modell_fuer
# ---------------------------------------------------------------------------

def test_modell_property() -> None:
    client = OllamaClient.aus_config(_config(modell="mistral:latest"))
    assert client.modell == "mistral:latest"


def test_modell_fuer_zuordnung() -> None:
    cfg = _config(modell="mistral:latest", modell_zuordnung={"beleg-extraktion": "llama3:8b"})
    client = OllamaClient.aus_config(cfg)
    assert client.modell_fuer("beleg-extraktion") == "llama3:8b"
    assert client.modell_fuer("anderer-skill") == "mistral:latest"


# ---------------------------------------------------------------------------
# generiere – Erfolgsfall
# ---------------------------------------------------------------------------

def test_generiere_gibt_response_zurueck() -> None:
    client = OllamaClient.aus_config(_config())
    with patch("urllib.request.urlopen", return_value=_mock_response({"response": "sieben"})):
        result = client.generiere("Nenne die Zahl 7")
    assert result == "sieben"


def test_generiere_mit_json_schema_sendet_format_parameter() -> None:
    client = OllamaClient.aus_config(_config())
    schema = {"type": "object", "properties": {"wert": {"type": "string"}}}
    captured_body: dict[str, Any] = {}

    def mock_open(req: Any, timeout: int = 0) -> Any:
        captured_body.update(json.loads(req.data))
        return _mock_response({"response": '{"wert":"ok"}'})

    with patch("urllib.request.urlopen", side_effect=mock_open):
        client.generiere("Test", json_schema=schema)

    assert "format" in captured_body
    assert captured_body["format"] == schema


def test_generiere_temperatur_aus_config() -> None:
    client = OllamaClient.aus_config(_config(temperatur=0.5))
    captured: dict[str, Any] = {}

    def mock_open(req: Any, timeout: int = 0) -> Any:
        captured.update(json.loads(req.data))
        return _mock_response({"response": "x"})

    with patch("urllib.request.urlopen", side_effect=mock_open):
        client.generiere("Test")

    assert captured["options"]["temperature"] == 0.5


# ---------------------------------------------------------------------------
# generiere – Fehler
# ---------------------------------------------------------------------------

def test_generiere_kein_modell_gibt_none() -> None:
    client = OllamaClient.aus_config(_config(modell=""))
    result = client.generiere("Test")
    assert result is None


def test_generiere_netzwerkfehler_gibt_none() -> None:
    client = OllamaClient.aus_config(_config())
    with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
        result = client.generiere("Test")
    assert result is None


def test_generiere_modell_nicht_installiert_gibt_none() -> None:
    client = OllamaClient.aus_config(_config())
    http_error = urllib.error.HTTPError(
        url="http://localhost:11434/api/generate",
        code=404,
        msg="Not Found",
        hdrs=MagicMock(),  # type: ignore[arg-type]
        fp=BytesIO(b'{"error":"model not found"}'),
    )
    with patch("urllib.request.urlopen", side_effect=http_error):
        result = client.generiere("Test")
    assert result is None


# ---------------------------------------------------------------------------
# ist_verfuegbar
# ---------------------------------------------------------------------------

def _multi_mock(responses: dict[str, dict[str, Any]]) -> Any:
    """Hilfsfunktion: gibt je nach URL-Ende das passende Mock zurück."""
    def side_effect(req: Any, timeout: int = 0) -> Any:
        url = req.get_full_url()
        for suffix, data in responses.items():
            if url.endswith(suffix):
                return _mock_response(data)
        raise ValueError(f"Unerwartete URL: {url}")
    return side_effect


def test_ist_verfuegbar_ok() -> None:
    client = OllamaClient.aus_config(_config())
    mock = _multi_mock({
        "/api/version": {"version": "0.5.1"},
        "/api/tags": {"models": [{"name": "mistral:latest"}]},
    })
    with patch("urllib.request.urlopen", side_effect=mock):
        ok, msg = client.ist_verfuegbar()
    assert ok is True
    assert "0.5.1" in msg


def test_ist_verfuegbar_modell_nicht_installiert() -> None:
    client = OllamaClient.aus_config(_config())
    mock = _multi_mock({
        "/api/version": {"version": "0.5.1"},
        "/api/tags": {"models": []},
    })
    with patch("urllib.request.urlopen", side_effect=mock):
        ok, msg = client.ist_verfuegbar()
    assert ok is False
    assert "ollama pull" in msg
    assert "mistral:latest" in msg


def test_ist_verfuegbar_normiert_modellname_ohne_tag() -> None:
    """'mistral' ohne ':latest' soll gegen 'mistral:latest' in /api/tags verglichen werden."""
    client = OllamaClient.aus_config(_config(modell="mistral"))
    mock = _multi_mock({
        "/api/version": {"version": "0.5.0"},
        "/api/tags": {"models": [{"name": "mistral:latest"}]},
    })
    with patch("urllib.request.urlopen", side_effect=mock):
        ok, _ = client.ist_verfuegbar()
    assert ok is True


def test_ist_verfuegbar_ollama_nicht_erreichbar() -> None:
    client = OllamaClient.aus_config(_config())
    with patch("urllib.request.urlopen", side_effect=OSError("refused")):
        ok, msg = client.ist_verfuegbar()
    assert ok is False
    assert "nicht erreichbar" in msg.lower()


def test_ist_verfuegbar_kein_modell() -> None:
    client = OllamaClient.aus_config(_config(modell=""))
    mock = _multi_mock({"/api/version": {"version": "0.5.0"}})
    with patch("urllib.request.urlopen", side_effect=mock):
        ok, msg = client.ist_verfuegbar()
    assert ok is False
    assert "Kein Modell" in msg


# ---------------------------------------------------------------------------
# pruefe_structured_output
# ---------------------------------------------------------------------------

def test_structured_output_unterstuetzt() -> None:
    client = OllamaClient.aus_config(_config())
    with patch("urllib.request.urlopen", return_value=_mock_response({"response": '{"ergebnis":"ok"}'})):
        assert client.pruefe_structured_output() is True


def test_structured_output_nicht_unterstuetzt() -> None:
    client = OllamaClient.aus_config(_config())
    with patch("urllib.request.urlopen", return_value=_mock_response({"response": "Kein JSON hier"})):
        assert client.pruefe_structured_output() is False


def test_structured_output_ollama_nicht_erreichbar() -> None:
    client = OllamaClient.aus_config(_config())
    with patch("urllib.request.urlopen", side_effect=OSError("refused")):
        assert client.pruefe_structured_output() is False
