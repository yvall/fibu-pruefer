"""LLM-Schicht: Protokoll, Ollama-Client, Null-Client.

Alle LLM-Aufrufe im Projekt laufen über dieses Paket.
"""
from .null import NullLlmClient
from .ollama import OllamaClient
from .protocol import LlmClient

__all__ = ["LlmClient", "NullLlmClient", "OllamaClient"]
