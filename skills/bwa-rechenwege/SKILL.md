---
name: bwa-rechenwege
description: >
  Prüft die Rechenwege der BWA (Monat und kumuliert): Gesamtleistung, Rohertrag,
  Betriebl. Rohertrag, Gesamtkosten, Betriebsergebnis, Neutraler Aufwand/Ertrag,
  Ergebnis vor Steuern, Vorläufiges Ergebnis.
kind: code
runs_after: []
severity_default: fehler
inputs:
  - auswertung.bwa
  - auswertung.month
  - auswertung.year
---

# bwa-rechenwege

## Wann anwenden

Immer wenn eine BWA-Seite vorliegt. Die Regel prüft, ob die ausgewiesenen Zwischensummen
rechnerisch aus den Einzelpositionen ableitbar sind – für den Berichtsmonat und kumuliert.

## Regeln

Jede der neun Formeln wird für Monat (idx 0) und kumuliert (idx 1) geprüft.
Differenz ≤ `toleranz` gilt als Rundungsdifferenz und erzeugt kein Finding.

| Zeile | Formel |
|---|---|
| Gesamtleistung | Umsatzerlöse + Best.Verdg. FE/UE + Akt.Eigenleistungen |
| Rohertrag | Gesamtleistung − Mat./Wareneinkauf |
| Betriebl. Rohertrag | Rohertrag + So. betr. Erlöse |
| Gesamtkosten | Summe der 11 Kostenarten (Personal, Raum, Steuern, Versicherungen, Besondere Kosten, Fahrzeug, Werbe-/Reise, Warenabgabe, AfA, Reparatur, Sonstiges) |
| Betriebsergebnis | Betriebl. Rohertrag − Gesamtkosten |
| Neutraler Aufwand | Zinsaufwand + Sonst. neutr. Aufw |
| Neutraler Ertrag | Zinserträge + Sonst. neutr. Ertr + Verr. kalk. Kosten |
| Ergebnis vor Steuern | Betriebsergebnis − Neutraler Aufwand + Neutraler Ertrag + Kontenkl. unbesetzt |
| Vorläufiges Ergebnis | Ergebnis vor Steuern − Steuern Eink.u.Ertr |

## Konfiguration

| Schlüssel | Standard | Beschreibung |
|---|---|---|
| `toleranz` | `0.02` | Maximale Differenz in € ohne Befund (aus `config/default.yaml`) |
