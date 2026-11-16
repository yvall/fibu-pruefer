---
name: entwicklung-ausreisser
description: >
  Prüft die 13-Monats-Entwicklungsübersicht gegen BWA-Werte und erkennt
  Ausreißer (Monatswert außerhalb der 12-Monats-Spanne) sowie stark
  abweichende Personalkosten.
kind: code
runs_after: []
severity_default: fehler
inputs:
  - auswertung.entwicklung
  - auswertung.bwa
  - auswertung.month
  - auswertung.entw_months
  - auswertung.ocr_pages
  - auswertung.page_types
---

# entwicklung-ausreisser

## Wann anwenden

Wenn eine Entwicklungsübersicht (13 Monate) vorhanden ist.

## Regeln

| Prüfung | Schwere |
|---|---|
| Monatswert Entwicklung ≠ BWA-Zeile (Toleranz 0,05 €) | fehler / pruefen bei OCR |
| Summe Jan–MM ≠ kumulierter BWA-Wert | fehler / pruefen bei OCR |
| Monatswert außerhalb der 12-Monats-Spanne (> 250 € und > 15 % vom Median) | info |
| Personalkosten-Abweichung > Schwelle | info |

Ausreißer-Prüfung überspringt aggregierte Zeilen: Gesamtleistung, Rohertrag,
Betriebl. Rohertrag, Gesamtkosten, Ergebnis vor Steuern.

## Konfiguration

| Schlüssel | Standard | Beschreibung |
|---|---|---|
| `personalkosten_ausreisser_schwelle` | `10000` | Schwellenwert in € |
