from __future__ import annotations

from fibu.llm.null import NullLlmClient
from fibu.llm.protocol import LlmClient


def test_null_client_implementiert_protocol() -> None:
    assert isinstance(NullLlmClient(), LlmClient)


def test_null_client_generiere_gibt_none() -> None:
    assert NullLlmClient().generiere("beliebiger Prompt") is None


def test_null_client_mit_schema_gibt_none() -> None:
    assert NullLlmClient().generiere("test", json_schema={"type": "object"}) is None


def test_null_client_modell() -> None:
    assert NullLlmClient().modell == "null"


def test_null_client_modell_fuer() -> None:
    assert NullLlmClient().modell_fuer("beleg-extraktion") == "null"
