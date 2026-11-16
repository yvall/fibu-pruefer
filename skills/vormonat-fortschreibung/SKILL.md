---
name: vormonat-fortschreibung
description: >
  Prüft Vormonats-Fortschreibung: kumulierte BWA-Werte (Vormonat + Monat = kumuliert),
  rückwirkend geänderte Konten und Konsistenz der Entwicklungsübersicht zwischen
  Vormonat und Berichtsmonat.
kind: code
runs_after: []
severity_default: fehler
inputs:
  - auswertung.bwa
  - auswertung.sus
  - auswertung.entwicklung
  - auswertung.entw_months
  - auswertung.month
  - auswertung.year
  - context.prev
---

# vormonat-fortschreibung

## Wann anwenden

Wenn `ctx.prev` gesetzt ist (Vormonats-BWA im Periodenordner vorhanden). Fehlt der
Vormonat, gibt der Skill ein `info`-Finding zurück und bricht nicht ab.

## Prüfungen

### 1. BWA-Fortschreibung (nur gleiches Jahr)

Für jede BWA-Zeile, die in beiden Monaten vorhanden ist:
```
kum. Vormonat + Monatswert = kum. Berichtsmonat
```
Abweichung > `toleranz` → `fehler` (Rückwirkungsbuchung).

### 2. Konten-Fortschreibung

Vergleicht kum. YTD-Werte (abzüglich aktuellem Monat) mit dem YTD des Vormonats.
Differenzen > `toleranz` → Liste geänderter Konten. Betrifft USt-Konten? → ACHTUNG-Hinweis.

Ergebnis wird als `_meta["changed"]` exportiert (Phase 2: befüllt `ctx.changed_accounts`).

### 3. Entwicklungsübersicht

Prüft, ob Monatswerte vergangener Monate unverändert geblieben sind. Toleranz 0,05 €.
OCR-Seiten senken Schwere auf `info`.

## Konfiguration

| Schlüssel | Standard | Beschreibung |
|---|---|---|
| `toleranz` | `0.02` | Toleranzgrenze für BWA- und Konten-Prüfung |
| `ustva_konto_vorsteuer` | `["1406","1401"]` | Vorsteuer-Konten (ACHTUNG-Hinweis) |
| `ustva_konto_ust_19` | `"3806"` | USt 19 % (ACHTUNG-Hinweis) |
| `ustva_konto_ust_13b` | `"3837"` | USt §13b (ACHTUNG-Hinweis) |
| `ustva_konto_vorsteuer_13b` | `"1407"` | Vorsteuer §13b (ACHTUNG-Hinweis) |
