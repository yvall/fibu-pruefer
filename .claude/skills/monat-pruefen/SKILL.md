---
name: monat-pruefen
description: Führt die Prüfung eines Periodenordners (z. B. "08 Aug") aus und fasst Monats- und Jahresergebnis, Fehler und offene Punkte zusammen. Verwenden, wenn ein Monat geprüft oder der Bericht erklärt werden soll.
disable-model-invocation: true
---

# Monat prüfen

Argument: Pfad zum Periodenordner (enthält `BWA/` und die Belegordner).

1. Prüfen, dass im `BWA/`-Ordner mindestens die aktuelle BWA liegt (Vormonat optional, aber empfohlen für die Fortschreibung).
2. Lauf starten: `python -m legacy.fibu_pruefer pruefen "<Ordner>"` (später: `python -m fibu pruefen`).
3. Den erzeugten Bericht unter `<Ordner>/Pruefbericht/` lesen.
4. Antwort in dieser Reihenfolge, kurz und auf Deutsch:
   - Ist das Monatsergebnis rechnerisch richtig? Ist das Jahresergebnis richtig und zum Vormonat konsistent?
   - Alle Fehler (rot) mit Konto/Beleg und Betrag.
   - Die drei wichtigsten Prüfhinweise (gelb).
   - Was nicht geprüft werden konnte (OCR-Seiten, unlesbare Belege, Personal- und Abschreibungskosten).
5. Keine Zahl aus dem Gedächtnis nennen, nur aus dem Bericht.
