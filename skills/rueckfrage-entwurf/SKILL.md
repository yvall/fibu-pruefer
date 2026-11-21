---
skill_id: rueckfrage-entwurf
name: Rückfragen-Entwurf
description: >
  Fasst Fehler- und Auffälligkeits-Befunde nach Themengruppe (Skill-ID) zusammen
  und erzeugt einen deterministischen Rückfragen-Entwurf an den Steuerberater.
  Zahlen kommen ausschließlich aus den Finding-Feldern, keine eigene Berechnung.
status: experimental
llm: optional
runs_after:
  - klaerungsliste
  - opos-pruefung
  - bwa-rechenwege
  - summen-salden
  - ergebnis-herleitung
  - saldenrichtung
  - wertenachweis-abgleich
  - ustva-abgleich
  - durchlaufende-posten
  - entwicklung-ausreisser
  - vormonat-fortschreibung
  - kosten-deckung
  - umsatz-beweis
  - belege-abgleich
inputs:
  - context.befunde
  - auswertung.periode
---

# Skill: rueckfrage-entwurf

## Ziel

Liest alle `Finding`-Objekte mit `severity in ("fehler", "pruefen")` aus den
vorausgegangenen Prüfskills und erzeugt daraus einen Rückfragen-Entwurf an den
Steuerberater. Die Fragen werden nach Themengruppen (Skill-ID) gegliedert.

## Deterministischer Kern (ohne LLM)

Je Finding entsteht eine Zeile nach dem Muster:

> Zu [Thema]: [Titel] – bitte prüfen und den Sachverhalt mitteilen.

Zahlen, Beträge, Kontonummern und Datumsangaben werden 1:1 aus dem
`Finding.title` übernommen; keine eigene Berechnung.

## Ausschlüsse

- Befunde mit `severity == "info"` werden nicht erneut aufgeführt.
- Eigene Befunde (`rule == "rueckfrage-entwurf"`) werden nicht re-gruppiert.

## Ausgabe

Pro Themengruppe ein `Finding(severity="info", rule="rueckfrage-entwurf")`.
Die Ergebnisaussage und der Exit-Code des Laufs bleiben unverändert.
Der Skill erscheint im Bericht im Abschnitt „KI-gestützt".
