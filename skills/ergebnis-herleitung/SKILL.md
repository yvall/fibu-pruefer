---
name: ergebnis-herleitung
description: >
  Unabhängiger Beweis des Ergebnisses: Summe der GuV-Konten (Klassen 4–8) aus
  Summen & Salden muss mit dem Vorläufigen Ergebnis der BWA übereinstimmen –
  für Monat und kumuliert.
kind: code
runs_after: []
severity_default: fehler
inputs:
  - auswertung.sus
  - auswertung.bwa
  - auswertung.month
  - auswertung.year
---

# ergebnis-herleitung

## Wann anwenden

Immer wenn sowohl Summen & Salden (GuV-Konten) als auch die BWA-Ergebniszeile
„Vorläufiges Ergebnis" vorhanden sind. Die Regel führt einen unabhängigen
Beweis des Ergebnisses durch – abweichend von der BWA-internen Arithmetik.

## Regeln

GuV-Konten: alle vierstelligen Konten der Klassen 4, 5, 6, 7, 8.

| Prüfung | Formel | Schwere |
|---|---|---|
| Monatsergebnis | Σ (Haben − Soll) der GuV-Konten = BWA „Vorläufiges Ergebnis" (Monat) | fehler |
| Jahresergebnis | Σ (kum. Haben − kum. Soll) der GuV-Konten = BWA „Vorläufiges Ergebnis" (kumuliert) | fehler |

Wenn keine GuV-Konten oder keine BWA-Ergebniszeile vorhanden: Befund „pruefen".

## Konfiguration

| Schlüssel | Standard | Beschreibung |
|---|---|---|
| `toleranz` | `0.02` | Toleranzgrenze in € |
