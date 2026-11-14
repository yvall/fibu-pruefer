---
name: neue-pruefregel
description: Legt eine neue deterministische Prüfregel (Code-Skill) für den Fibu-Prüfer an, mit SKILL.md, check.py und Tests. Verwenden, wenn eine neue Buchhaltungs-Prüfung ergänzt werden soll.
disable-model-invocation: true
---

# Neue Prüfregel anlegen

Argument: kurze Beschreibung der Regel, z. B. "Abschreibungen gegen Anlagenverzeichnis prüfen".

## Vorgehen
1. Regel-ID in kebab-case wählen (z. B. `afa-anlagenverzeichnis`), prüfen, dass `skills/<id>/` nicht existiert.
2. `skills/<id>/SKILL.md` anlegen mit Frontmatter `name`, `description`, `kind: code`, `runs_after`,
   `severity_default`, `inputs` und den Abschnitten "Wann anwenden" und "Regeln" (Formeln mit Kontonummern aus `config/`).
3. `skills/<id>/check.py` mit `def run(ctx: Context) -> list[Finding]`. Nur reine Funktionen, `Decimal`, kein Netzwerk, kein LLM.
4. Jeder `Finding` enthält `rule`, `severity`, `title`, `detail`, `calc` (erwartet, ist, Differenz, Formel) und `refs`.
5. Tests unter `skills/<id>/tests/`: ein Fall ohne Befund, ein Fall mit Befund, ein Randfall (Toleranz 0,02 €).
6. `pytest skills/<id>/tests -q`, `ruff check` und `mypy` ausführen und Ergebnis berichten.

## Nicht tun
- Keine Kontonummern oder Schwellen hartkodieren, sie gehören in die Konfiguration.
- Keine echten Mandantendaten in Tests.
