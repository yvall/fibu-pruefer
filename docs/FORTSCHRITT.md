# Fortschritt Phase 3 – LLM-Skills

## Schritt 3a – LLM-Adapter ✓

Neue Pakete und Änderungen:

| Datei / Paket | Inhalt |
|---|---|
| `src/fibu/llm/__init__.py` | Exports: `LlmClient`, `OllamaClient`, `NullLlmClient` |
| `src/fibu/llm/protocol.py` | `LlmClient` Protocol (`@runtime_checkable`): `modell`, `modell_fuer(skill_id)`, `generiere(prompt, json_schema)` |
| `src/fibu/llm/ollama.py` | `OllamaClient`: `generiere()` via `urllib.request`, Temperatur 0.0, `json_schema` als Ollama-`format`-Parameter; `ist_verfuegbar()` prüft Erreichbarkeit und Modell-Installation; `pruefe_structured_output()`; `# noqa: BLE001` für intentionell breite Netzwerk-Exceptions |
| `src/fibu/llm/null.py` | `NullLlmClient`: `generiere()` immer `None` (Tests, Trockenlauf) |
| `src/fibu/config.py` | `LlmConfig(anbieter, url, modell, temperatur=0.0, timeout_sekunden=120, modell_zuordnung)`; in `LokaleConfig.laden()` überschreibt `FIBU_LLM_MODELL` nur das Modell |
| `config/lokal.example.yaml` | `llm:`-Abschnitt mit `modell_zuordnung`-Beispiel |
| `config/default.yaml` | Platzhalter-Kommentar (kein Standardmodell im Repo) |
| `src/fibu/cli.py` | `fibu llm pruefen`: zeigt Konfiguration, prüft Erreichbarkeit, Modell-Installation, Structured-Output-Unterstützung und macht Test-Aufruf; Exit 0/2 |

**Fallback-Kette:** `FIBU_LLM_MODELL` > `llm.modell` in `lokal.yaml` > leer (kein LLM).
Leeres Modell = kein Netzaufruf, `generiere()` → `None` → LLM-Skills erzeugen „nicht verfügbar"-Findings.
Modell konfiguriert aber nicht installiert = Meldung mit `ollama pull <modell>`.

30 neue Tests (unit/llm). 270 Tests grün.

---

# Fortschritt Phase 1 – Fundament

## Erledigte Schritte

| Schritt | Commit | Inhalt |
|---|---|---|
| 0 Vorbereitung | `69f9c2c` | Startpaket, git init |
| 1 Bestandsaufnahme | _(Plan Mode, kein Commit)_ | Migrationstabelle, Reihenfolge, Risiken |
| 2 Verträge | `88376de` | `src/fibu/contracts/` – Pydantic-Modelle |
| 3 Skill-Loader | `88376de` | `src/fibu/skills_runtime/` – Loader, Scheduler, Runner |
| 4 Golden-Test | `407aff6` | `tests/golden/`, `conftest.py` |

---

# Fortschritt Phase 2 – Graph

## Entscheidungen für 2b und 2c

Diese Festlegungen gelten ab Phase 2b und sind bei der Umsetzung verbindlich:

**E1 – Knotenreihenfolge und Interrupt-Bedingung**
Reihenfolge: `bewerte → erstelle_bericht → warte_auf_freigabe → versand`.
`warte_auf_freigabe` wird nur eingehängt, wenn `--mail` übergeben wird.
Ohne `--mail` endet der Graph nach `erstelle_bericht` ohne Interrupt.

**E2 – Lauf-ID und Freigabe-Workflow**
Jeder Lauf erhält eine eigene UUID als Lauf-ID (nicht hash des Ordners).
`fibu freigeben` sucht den jüngsten offenen Lauf für den Periodenordner.
Mehrere parallele Läufe auf demselben Ordner sind damit möglich.

**E3 – Schlanker State, Serialisierung testen**
Der Graph-State hält das vollständige `Context`-Objekt nur in Phase 2a.
Ab 2b: State enthält nur IDs und primitive Werte; `Context` und `Auswertung`
werden über `LaufStore` nachgeladen. Tests prüfen explizit `Decimal`- und
`Path`-Serialisierung mit dem SQLite-Checkpointer.

**E4 – Stabile Finding-ID**
`Finding.id` = `sha256("{rule}:{fachlicher-schluessel}")[:16]`, wobei der
fachliche Schlüssel aus dem Skill selbst kommt (z. B. Kontonummer, Belegpfad).
Für Befunde ohne `refs` wird `rule` allein als Schlüssel verwendet.
Testanforderung: Alle `id`-Werte in einem Lauf sind eindeutig.

**E5 – SQLite-Pfad aus Konfiguration**
`config/lokal.yaml` (außerhalb des Repos, in `.gitignore`) enthält den
`store.sqlite_pfad`-Schlüssel. Fallback: `~/.fibu/laeufe.db`.
`config/default.yaml` enthält nur den Platzhalter-Kommentar.

## Schritt 2c – Versand-Knoten ✓

Neue Pakete und Änderungen:

| Datei / Paket | Inhalt |
|---|---|
| `src/fibu/ingest/mail.py` | `MailSender` Protocol, `SmtpMailSender` (STARTTLS, Passwort aus `FIBU_SMTP_PASS` oder `lokal.yaml`), `NullMailSender` (Trockenlauf). Empfänger ausschließlich aus `MailConfig.an`. |
| `src/fibu/config.py` | `MailConfig` (smtp\_host/port/user/pass, von, an); eingebaut in `LokaleConfig`. |
| `config/lokal.example.yaml` | `mail:`-Abschnitt mit Anti-Injection-Hinweis. |
| `src/fibu/store/sqlite.py` | Spalte `versand_ok` (Migration via try/except); `setze_versand_ok()`, `ist_versand_ok()`. |
| `src/fibu/graph/state.py` | Optionales Feld `versand_ok: bool`. |
| `src/fibu/graph/nodes.py` | Knoten `versand`: idempotent, No-op bei gesperrter/fehlender Freigabe. |
| `src/fibu/graph/graph.py` | `create_graph(mail_sender=…)`; Kante `warte_auf_freigabe → versand → END`. |
| `src/fibu/graph/runner.py` | `freigeben_lauf(trocken=…, _mail_sender=…)`; Status „gesperrt" bei abgelehnter Freigabe. |
| `src/fibu/cli.py` | `fibu freigeben --trocken`; Ausgabe „Versand: ok (Trockenlauf)". |

22 neue Tests (unit/ingest, unit/store, unit/graph, integration). 240 Tests grün.

---

## Schritt 2b – Persistenz, Finding-IDs, Freigabe ✓

Neue Pakete und Änderungen:

| Datei / Paket | Inhalt |
|---|---|
| `src/fibu/contracts/finding.py` | `Finding.id` als `@computed_field`; `id_suffix` für Runtime-Deduplication; `schema_version = "2"`. Normalisierung: Ziffern und Beträge werden aus Formel/Titel-Fallback entfernt (gleiches Muster, anderer Betrag → gleiche ID). |
| `src/fibu/store/` | `LaufStore` (SQLite, Tabellen `laeufe`, `kontext`, `findings`); `Context`-JSON-Roundtrip via Pydantic v2 `model_dump_json()`/`model_validate_json()`; Dateirechte 0600 bei Neuanlage. **ACHTUNG:** Datei enthält echte Finanzdaten – Pfad aus `config/lokal.yaml` (`store.sqlite_pfad`), Standard: `~/.fibu/laeufe.db`. |
| `src/fibu/graph/state.py` | `lauf_id` und `mit_mail` als Pflichtfelder; kein `kontext` im State (E3); `entscheidung: Entscheidung` optional. |
| `src/fibu/graph/nodes.py` | Alle Knoten store-aware (Closures); `bewerte` dedupliciert Finding-IDs (Suffix `#2`, `#3`…) und erzeugt info-Finding bei Kollision; `warte_auf_freigabe` ruft `interrupt()` nur bei `mit_mail=True`. |
| `src/fibu/graph/graph.py` | `create_graph(store, checkpointer)`; MSGPACK-Allowlist für `SkillResult`/`Finding`/`Calc`/`Ref` beim SqliteSaver. |
| `src/fibu/graph/runner.py` | `run_pruefung()` mit UUID-Lauf-ID, `MemorySaver`/`SqliteSaver` je nach `mit_mail`; `freigeben_lauf()` resume via `Command(resume=…)`. |
| `src/fibu/cli.py` | `--mail` Flag; `freigeben`-Subkommando (sucht neuesten offenen Lauf). |
| `src/fibu/config.py` | `StoreConfig` mit `sqlite_pfad`. |
| `src/fibu/report.py` | Bugfix: HTML-Offset-Fehler bei `- **…**`-Zeilen (Position 4 statt 6). |

31 neue Tests (unit/contracts, unit/store, unit/graph, integration). 218 Tests grün.

---

## Schritt 2a – Minimaler Graph ✓

`src/fibu/graph/` mit typisiertem `PruefState` (TypedDict), vier Knoten
(`lade_kontext`, `fuehre_skills_aus`, `bewerte`, `erstelle_bericht`) und
`run_pruefung()` als Einstiegspunkt. `python -m fibu pruefen` nutzt den Graph.
16 neue Tests (unit/graph + integration/graph_pipeline). 187 Tests grün.

---

## Schritt 2 – Contracts (`src/fibu/contracts/`)

Pydantic-v2-Modelle mit `schema_version = "1"`:

| Datei | Öffentliche Typen |
|---|---|
| `finding.py` | `Ref`, `Calc`, `Finding` |
| `auswertung.py` | `Konto`, `WKonto`, `WGroup`, `OposItem`, `JahresEintrag`, `JahresKonto`, `Rueckfrage`, `UstvaKz`, `Auswertung` |
| `beleg.py` | `BelegRecord` |
| `entscheidung.py` | `Entscheidung` |
| `context.py` | `KlaerRow`, `ChangedKonto`, `Context` |

**`Finding`:**
```python
class Finding(BaseModel):
    schema_version: str = "1"
    rule: str                              # Regel-ID, z. B. "bwa-rechenwege"
    severity: Literal["fehler", "pruefen", "info"]
    title: str
    detail: str
    calc: Calc | None = None               # erwartet, ist, differenz, formel
    refs: list[Ref] = []                   # art: "seite"|"konto"|"beleg"
```

**`Context`:**
```python
class Context(BaseModel):
    auswertung: Auswertung
    prev: Auswertung | None = None         # Vormonats-BWA
    belege: list[BelegRecord] = []
    klaerung: list[KlaerRow] = []
    changed_accounts: list[tuple[str, str, Decimal, Decimal]] = []
    config: dict[str, object] = {}
```

Wichtige Entscheidungen: `page_texts: list[str]` statt `pages: list[Page]`,
`ustva: dict[str, UstvaKz]` mit `tax: Decimal | None` (None-Semantik wie Legacy),
keine `from_legacy`/`to_legacy` im contracts-Paket selbst.

32 Tests in `tests/unit/contracts/`.

---

## Schritt 3 – Skills-Runtime (`src/fibu/skills_runtime/`)

```python
results: list[SkillResult] = run_skills(ctx, skills_dir=Path("skills"))
```

Jedes `skills/<id>/check.py` implementiert `def run(ctx: Context) -> list[Finding]`.
SKILL.md-Frontmatter (`runs_after`, `inputs`) steuert Ausführungsreihenfolge.
Fehler → Finding „Prüfung nicht durchgeführt", kein Laufabbruch.

26 Tests in `tests/unit/skills_runtime/`.

---

## Schritt 4 – Golden-Test (`tests/golden/`)

```bash
# Referenz anlegen (erster Lauf):
FIBU_GOLDEN_DIR="/pfad/zum/ordner" pytest tests/golden -v

# Vergleich (Folgeläufe):
FIBU_GOLDEN_DIR="/pfad/zum/ordner" pytest tests/golden -v

# Referenz explizit erneuern:
FIBU_GOLDEN_UPDATE=1 FIBU_GOLDEN_DIR="/pfad/zum/ordner" pytest tests/golden -v
```

Die Referenzdatei `golden_findings.json` liegt im Periodenordner **außerhalb des Repos**
und wird nie committet. Verglichen werden strukturierte Befunde:
`{check, severity, title, detail}` – kein Layout, keine Timestamps.

`conftest.py` (Projektwurzel) stellt `make_auswertung()` und `make_context()` als
Pytest-Fixture-Factories für Skill-Unit-Tests bereit (gültig für `tests/` und `skills/`).

Externe Abhängigkeiten: `pdftotext`, `pdftoppm` (poppler), `tesseract` –
alle drei in `~/opt/anaconda3/bin/`.

---

## CLI für die manuelle Prüfung ✓

`python -m fibu pruefen --ordner "<Periodenordner>"` nutzt die neue Skills-Runtime:

- `src/fibu/ingest/` – Konvertierung legacy.Auswertung → contracts.Auswertung,
  Belege und Klärungsliste laden
- `src/fibu/report.py` – Markdown + HTML aus `list[SkillResult]`
- `python -m fibu pruefen --legacy` – schaltet auf den alten Pipeline-Pfad zurück

Der Legacy-Einstiegspunkt `python -m legacy.fibu_pruefer pruefen "<Ordner>"` bleibt
erhalten. Phase 1 ist damit abgeschlossen.

---

## Schritt 5 – Regelmigration (laufend)

Reihenfolge laut `docs/PROMPTS_PHASE_1.md`:

| Welle | Skill-ID | Legacy-Funktion | Status |
|---|---|---|---|
| 1 | `bwa-rechenwege` | `check_bwa_arithmetik` | ✓ migriert |
| 1 | `summen-salden` | `check_summen_salden` | ✓ migriert |
| 1 | `ergebnis-herleitung` | `check_ergebnis_aus_konten` | ✓ migriert |
| 1 | `saldenrichtung` | `check_kontenrichtung` | ✓ migriert |
| 2 | `wertenachweis-abgleich` | `check_wertenachweis` | ✓ migriert |
| 2 | `ustva-abgleich` | `check_ustva` | ✓ migriert |
| 2 | `opos-pruefung` | `check_opos` | ✓ migriert |
| 2 | `durchlaufende-posten` | `check_durchlaufend` | ✓ migriert |
| 2 | `entwicklung-ausreisser` | `check_entwicklung` | ✓ migriert |
| 3 | `vormonat-fortschreibung` | `check_vormonat` | ✓ migriert |
| 4 | `kosten-deckung` | `check_deckung` | ✓ migriert |
| 4 | `umsatz-beweis` | `check_umsatz` | ✓ migriert |
| 4 | `belege-abgleich` | `check_belege` | ✓ migriert |
| 5 | `klaerungsliste` | `check_klaerung` | ✓ migriert |

Strategie: jeder Skill beginnt als **Thin Wrapper** (ruft Legacy-Funktion auf,
konvertiert `legacy.Finding → contracts.Finding`). Der Golden-Test muss nach
jeder Migration grün bleiben. Für Thin Wrapper werden `Auswertung.from_legacy()`
und `Auswertung.to_legacy()` in `src/fibu/contracts/auswertung.py` ergänzt.
