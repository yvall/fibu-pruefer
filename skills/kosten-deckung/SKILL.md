---
name: kosten-deckung
description: >
  Grobabgleich auf Summenebene: gebuchte Belegkosten (netto + Vorsteuer)
  gegen Summe der Eingangsbelege.
kind: code
runs_after: []
severity_default: pruefen
inputs:
  - auswertung.sus
  - context.belege
---
