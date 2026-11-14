# Prompt-Reihenfolge für Phase 1 (Fundament)

Ziel von Phase 1: Verträge, Skill-Loader und ausgelagerte Prüfregeln. Das Ergebnis des August-Berichts darf sich
nicht ändern (Golden-Test). Arbeite in kleinen Schritten, und starte jeden Schritt mit einem frischen `/clear`,
wenn der vorige abgeschlossen und committet ist.

## 0. Vorbereitung (einmalig)
1. Ordner als Git-Repository anlegen: `git init`, erster Commit mit diesem Startpaket.
2. `claude` im Projektordner starten, danach `/init` ausführen, damit Claude den Code kennenlernt, und die
   mitgelieferte `CLAUDE.md` prüfen (nicht überschreiben lassen, nur ergänzen).
3. Plan Mode für Schritt 1 und 2 nutzen: `Shift+Tab` wechselt den Berechtigungsmodus.

## 1. Bestandsaufnahme (Plan Mode, nichts ändern)
> Lies `legacy/fibu_pruefer/` und `CLAUDE.md`. Erstelle einen Plan, wie wir die `check_*`-Funktionen aus `checks.py`
> und `belege.py` in Skills unter `skills/` überführen, ohne dass sich das Ergebnis ändert. Liste je Funktion Eingaben,
> Ausgaben und Abhängigkeiten. Schlage eine Reihenfolge vor und nenne Risiken.

## 2. Verträge
> Lege `src/fibu/contracts/` an mit Pydantic-Modellen `Auswertung`, `BelegRecord`, `Finding`, `Calc`, `Ref` und
> `Entscheidung` nach dem Plan. Das bestehende `Finding`-Dataclass aus `legacy` ist die Vorlage. Schreibe Tests
> für Validierung und Serialisierung.

## 3. Skill-Loader
> Implementiere `src/fibu/skills_runtime/`: Der Loader findet `skills/*/SKILL.md`, liest das Frontmatter, sortiert
> nach `runs_after` und führt unabhängige Skills parallel aus. Ein fehlerhafter Skill erzeugt ein Finding
> "Prüfung nicht durchgeführt" und bricht den Lauf nicht ab. Mit Tests.

## 4. Golden-Test aufbauen
> Erzeuge aus dem anonymisierten Beispielmonat in `tests/fixtures/` den Golden-Bericht mit dem Legacy-Code und
> speichere ihn unter `tests/golden/`. Dieser Test ist ab jetzt die Messlatte für jede Migration.

## 5. Regeln migrieren (je Regel ein Durchlauf)
> Nutze `/neue-pruefregel` für `bwa-rechenwege` und migriere `check_bwa_arithmetik` dorthin. Danach Golden-Test.

Wiederhole Schritt 5 für `wertenachweis-abgleich`, `summen-salden`, `ergebnis-herleitung`, `vormonat-fortschreibung`,
`ustva-abgleich`, `opos-pruefung`, `durchlaufende-posten`, `saldenrichtung`, `entwicklung-ausreisser`,
`umsatz-beweis`, `kosten-deckung`, `klaerungsliste`.

## Gewohnheiten, die Zeit sparen
- Ein Schritt, ein Commit: `commit die Änderungen mit einer deutschen Nachricht`.
- Wenn Claude zweimal dasselbe falsch macht, gehört die Regel in `CLAUDE.md`.
- Wiederkehrende Abläufe werden Skills (wie `/monat-pruefen`).
- Echte Daten bleiben außerhalb des Repos; für Experimente mit echten PDFs den Ordner per `--add-dir` freigeben
  oder die Dateien außerhalb ablegen und nur den Pfad nennen.
