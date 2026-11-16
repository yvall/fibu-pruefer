---
name: wertenachweis-abgleich
description: >
  Prüft den Wertenachweis: Kontensummen gegen BWA-Zeilen, Wertenachweis gegen
  BWA-Seite (Fuzzy-Match) und einzelne Konten gegen Summen & Salden.
kind: code
runs_after: []
severity_default: fehler
inputs:
  - auswertung.wgroups
  - auswertung.bwa
  - auswertung.sus
---

# wertenachweis-abgleich

## Konfiguration

| Schlüssel | Standard | Beschreibung |
|---|---|---|
| `toleranz` | `0.02` | Toleranzgrenze in € |
