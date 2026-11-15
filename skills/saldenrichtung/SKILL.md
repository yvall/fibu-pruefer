---
name: saldenrichtung
description: >
  Prüft, ob Konten auf der erwarteten Seite stehen (SKR04-Richtungsregel),
  ob Monatssummen negativ sind (Storno-Hinweis) und ob Personenkonten auf
  der richtigen Seite saldieren.
kind: code
runs_after: []
severity_default: pruefen
inputs:
  - auswertung.sus
---

# saldenrichtung

## Wann anwenden

Immer wenn Summen & Salden vorhanden sind.

## Regeln

### Erwartete Saldenrichtung (SKR04)

| Kontoklasse | Erwartung |
|---|---|
| 0 (Anlagevermögen) | Soll |
| 1 (Umlaufvermögen) | Soll |
| 3 (Verbindlichkeiten) | Haben |
| 4 (Erlöse) | Haben |
| 6 (Aufwand) | Soll |
| 7 (Aufwand) | Soll |

Konten mit Mindest-Saldo < `saldenrichtung_min_saldo` werden nicht geprüft.
Konten in `saldenrichtung_skip` werden ausgenommen (atypische Richtung zulässig).

### Negative Monatssummen

Werden als `info` gemeldet (Hinweis auf Storno oder Gegenbuchung).

### Personenkonten falsche Seite

5-stellige Konten mit Präfix „1" (Debitoren) oder „7" (Kreditoren): Soll = +,
Haben = −. Abweichung → `pruefen`.

## Konfiguration

| Schlüssel | Standard | Beschreibung |
|---|---|---|
| `toleranz` | `0.02` | Toleranzgrenze in € |
| `saldenrichtung_min_saldo` | `1.00` | Mindest-Saldo für Richtungsprüfung |
| `saldenrichtung_skip` | `["2910","3820","3830","4946","1370","6850_"]` | Konten ohne Richtungsprüfung |
