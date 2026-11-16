---
name: ustva-abgleich
description: >
  Prüft UStVA-Kennzahlen (81, 66, 46, 67, 83) gegen Buchhaltungskonten:
  Bemessungsgrundlagen, Steuerbeträge, Zahllast, Verbindlichkeit USt,
  Übermittlungsprotokoll und Datumslogik.
kind: code
runs_after: []
severity_default: fehler
inputs:
  - auswertung.ustva
  - auswertung.sus
  - auswertung.ustva_zahllast
  - auswertung.ustva_datum
  - auswertung.letter_amount
  - auswertung.page_texts
---

# ustva-abgleich

## Konfiguration

| Schlüssel | Standard | Beschreibung |
|---|---|---|
| `toleranz` | `0.02` | Allgemeine Toleranz in € |
| `ustva_konto_ust_19` | `"3806"` | Umsatzsteuer 19 % |
| `ustva_konto_vorsteuer` | `["1406","1401"]` | Vorsteuer-Konten |
| `ustva_konto_ust_13b` | `"3837"` | USt § 13b |
| `ustva_konto_vorsteuer_13b` | `"1407"` | Vorsteuer § 13b |
| `ustva_konto_zahlung` | `"3820"` | USt-Vorauszahlung |
| `ustva_konto_verbindlichkeit` | `"3860"` | USt-Verbindlichkeit |
