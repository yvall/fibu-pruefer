"""Optionale lokale LLM-Anbindung (Ollama). Zahlen werden NIE vom LLM berechnet –
nur Formulierung (Zusammenfassung) und Feldextraktion aus unstrukturierten Belegen."""
from __future__ import annotations

import json
import os
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")


def generate(prompt: str, model: str | None = None, timeout: int = 180) -> str | None:
    body = json.dumps({"model": model or OLLAMA_MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.1}}).encode()
    req = urllib.request.Request(OLLAMA_URL, body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())["response"].strip()
    except Exception:  # noqa: BLE001 – Ollama nicht erreichbar -> still weiter ohne LLM
        return None


def summarize(findings_text: str) -> str | None:
    return generate(
        "Du bist Buchhaltungs-Reviewer. Fasse die folgenden, bereits nachgerechneten Prüfbefunde in höchstens "
        "6 Sätzen auf Deutsch für den Geschäftsführer zusammen. Verwende ausschließlich die genannten Zahlen, "
        "erfinde nichts.\n\n" + findings_text)


def extract_beleg_fields(text: str) -> dict | None:
    out = generate(
        "Extrahiere aus dem Beleg als reines JSON: {\"art\":\"rechnung|gutschrift|quittung\",\"nummer\":str,"
        "\"datum\":\"TT.MM.JJJJ\",\"brutto\":number,\"netto\":number,\"ust\":number,\"aussteller\":str}. "
        "Keine Erklärung.\n\n" + text[:6000])
    if not out:
        return None
    try:
        return json.loads(out[out.index("{"): out.rindex("}") + 1])
    except Exception:  # noqa: BLE001
        return None
