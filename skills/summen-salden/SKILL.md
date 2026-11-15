---
name: summen-salden
description: >
  Prüft die interne Konsistenz der Summen & Salden: Saldo = EB + Soll − Haben,
  doppelte Buchhaltung (Monat und kumuliert), Eröffnungsbilanz ausgeglichen,
  Saldensumme = 0, Summenzeilen-Plausibilität, Personenkonten ↔ Sammelkonten.
kind: code
runs_after: []
severity_default: fehler
inputs:
  - auswertung.sus
  - auswertung.sus_total
---

# summen-salden

## Wann anwenden

Immer wenn Summen & Salden vorhanden sind. Die Regel prüft die rechnerische
Integrität des Summen-und-Salden-Ausdrucks unabhängig von der BWA.

## Regeln

| Prüfung | Schwere |
|---|---|
| Saldo = EB + Σ Soll − Σ Haben (je Konto) | fehler |
| Σ Monat Soll = Σ Monat Haben (nur Sachkonten ≤ 4 Stellen) | fehler |
| Σ kum. Soll = Σ kum. Haben (nur Sachkonten ≤ 4 Stellen) | fehler |
| Σ EB = 0 (nur Sachkonten ≤ 4 Stellen) | fehler |
| Σ Salden = 0 (nur Sachkonten ≤ 4 Stellen) | fehler |
| Summenzeile Monat Soll ≠ errechnete Summe | pruefen |
| Summenzeile kum. Soll ≠ errechnete Summe | pruefen |
| Summe Personenkonten ≠ Sammelkonto | fehler |

Personenkonten: 5-stellige Kontonummern mit Präfix "1" (Debitoren) oder "7"
(Kreditoren). Sammelkonten aus `ctx.config`.

## Konfiguration

| Schlüssel | Standard | Beschreibung |
|---|---|---|
| `toleranz` | `0.02` | Toleranzgrenze in € |
| `debitoren_sammelkonto` | `"1200"` | SKR04-Sammelkonto Debitoren |
| `kreditoren_sammelkonto` | `"3300"` | SKR04-Sammelkonto Kreditoren |
