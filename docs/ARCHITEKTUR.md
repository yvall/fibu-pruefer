# Architektur (Kurzfassung)

Das vollständige Konzept mit Diagrammen liegt im Dokument "Fibu-Prüfer als Multi-Agenten-System: Konzept & Architektur".
Hier steht, was Claude Code für die Arbeit braucht.

## Schichten
1. Auslöser: Ordner-Watcher, IMAP, Cron, CLI
2. Orchestrierung: LangGraph-Graph (Lauf starten, Auswertung lesen, Belege lesen, Prüfen, Bewerten, Rückfrage entwerfen, Freigabe, Bericht, Versand)
3. Fähigkeiten: Skills-Registry (Code-Skills für Prüfregeln, LLM-Skills für Lesen, Zuordnen, Formulieren)
4. Adapter: PDF/OCR, Belegquelle, LLM (Ollama), Datenbank, Mail

## Verträge zwischen Agenten
`Auswertung`, `BelegRecord`, `Finding`, `Entscheidung` (Pydantic, mit `schema_version`).

## Ordnerstruktur (Ziel)
```
src/fibu/{contracts,graph,agents,skills_runtime,ingest,report,llm,store}/
skills/<regel-id>/{SKILL.md,check.py,tests/}
skills_custom/        # Mandanten-Skills, überschreiben Standard
config/{default.yaml,mandant_if2it.yaml}
tests/{fixtures,golden}/   evals/
```

## Phasen
1 Fundament · 2 Graph · 3 LLM-Skills · 4 Betrieb · 5 Erweiterung. Jede Phase endet an einem Tor
(siehe Roadmap im Konzeptdokument).
