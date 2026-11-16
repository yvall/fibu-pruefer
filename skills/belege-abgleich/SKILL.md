---
name: belege-abgleich
description: >
  Prüft Belege und Gutschriften gegen offene Posten: Vollständigkeit, Dubletten,
  Betragskonsistenz, Rückfragen des Steuerberaters, Belege ohne Gegenstück.
kind: code
runs_after: []
severity_default: pruefen
inputs:
  - auswertung.opos
  - auswertung.sus
  - auswertung.rueckfragen
  - context.belege
---
