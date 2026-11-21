---
skill_id: beleg-extraktion
beschreibung: >
  Extrahiert Betrag, Datum und Belegnummer aus Belegen,
  die der deterministische Parser nicht auswerten konnte,
  per LLM. Nur Belege ohne erkannte Beträge (alle=[]) werden
  verarbeitet – alle anderen überspringt der Skill.
llm: true
status: experimental
runs_after: []
inputs:
  - context.belege
---

# Skill: beleg-extraktion

## Ziel

Belege, bei denen der deterministische Parser keinen Betrag erkennen konnte
(z. B. schlechte Scan-Qualität), werden einem LLM zur Extraktion übergeben.

## Invarianten

- Nur Belege mit `alle == []` und `kind != "storno"` werden verarbeitet.
- Jeder extrahierte Wert muss im Originaltext vorkommen (Guard gegen Halluzination).
- `Finding.calc` und `Finding.refs` werden ausschließlich deterministisch gesetzt.
- LLM-Output erscheint nur in `Finding.detail` und `Finding.title`,
  nach Pydantic-Validierung.
- Das Modell kommt ausschließlich aus der Konfiguration:
  `llm.modell_zuordnung["beleg-extraktion"]` oder `llm.modell`.

## Guard

Jedes nicht-leere extrahierte Feld wird gegen den Originaltext geprüft.
Variationen: DE-Format "1.234,56" ↔ EN-Format "1234.56", Whitespace.
Bei Guard-Fehler: Finding mit `severity="pruefen"`.

## Fallback ohne LLM

Wenn kein LLM konfiguriert ist, gibt die Skills-Runtime automatisch ein
`severity="info"` Finding "LLM nicht konfiguriert" zurück (via E7).
