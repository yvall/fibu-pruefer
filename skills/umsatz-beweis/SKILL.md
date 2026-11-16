---
name: umsatz-beweis
description: >
  Belegt Umsatzerlöse durch Gutschriften des Leistungsmonats und prüft
  Netto × 1,19 ↔ gebuchter Betrag.
kind: code
runs_after: []
severity_default: fehler
inputs:
  - auswertung.sus
  - auswertung.opos
  - context.belege
---
