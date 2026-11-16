---
name: durchlaufende-posten
description: >
  Prüft Jahreskonten (z. B. Durchlaufende Posten): Saldo-Konsistenz,
  Einzelposten vs. Summenzeile, offene Salden, Doppelbuchungen,
  überfällige Posten und Klärungsvermerke.
kind: code
runs_after: []
severity_default: fehler
inputs:
  - auswertung.jahreskonten
  - auswertung.created
---

# durchlaufende-posten

## Konfiguration

| Schlüssel | Standard | Beschreibung |
|---|---|---|
| `toleranz` | `0.02` | Toleranzgrenze in € |
| `ueberfaellig_tage` | `60` | Alter in Tagen ab dem ein offener Posten als info gemeldet wird |
