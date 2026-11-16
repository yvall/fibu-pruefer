---
name: opos-pruefung
description: >
  Prüft die Offene-Posten-Liste: Saldoabgleich mit Summen & Salden,
  Sammelkonten, doppelte Rechnungsnummern, Rechnungen nach Periodenende
  und überfällige Forderungen.
kind: code
runs_after: []
severity_default: fehler
inputs:
  - auswertung.opos
  - auswertung.sus
  - auswertung.year
  - auswertung.month
  - auswertung.created
---

# opos-pruefung

## Konfiguration

| Schlüssel | Standard | Beschreibung |
|---|---|---|
| `toleranz` | `0.02` | Toleranzgrenze in € |
| `debitoren_sammelkonto` | `"1200"` | SKR04-Sammelkonto |
| `kreditoren_sammelkonto` | `"3300"` | SKR04-Sammelkonto |
