# Fortschritt Phase 3 – LLM-Skills

**Stand: 2026-11-24 · Letzter Commit: `1474586` · Tests: 563 (19 übersprungen; mit FIBU_GOLDEN_DIR 582)**

## Gesamtstand Phase 3

| Schritt | Inhalt | Status |
|---|---|---|
| 3a | LLM-Adapter (`LlmClient`, `OllamaClient`, `NullLlmClient`) | ✓ |
| 3b | LLM-Integration Skills-Runtime | ✓ |
| 3c | LLM-Skill `beleg-extraktion` (deterministischer Betrag + LLM-Datum/Nr.) | ✓ experimentell |
| 3d | `beleg-zuordnung` – Belege deterministisch Konten/Findings zuordnen | ⏳ offen |
| 3e | Skill `rueckfrage-entwurf` – Rückfragen-Entwurf mit LLM-Formulierung | ✓ experimentell |
| Phase 4 | IMAP-Trigger, Ordner-Watcher | ⏳ offen |

---

## Schritt 3e – Skill `rueckfrage-entwurf` ✓ (experimentell)

### Commits

| Teilschritt | Commit | Inhalt |
|---|---|---|
| 3e-1 | `38f7fc1` | `Context.befunde` + Runtime-Befüllung; `llm: optional`-Flag; befunde_skills laufen nach allen normalen Skills |
| 3e-2 | `7b4ceab` | Deterministischer Kern: Markdown-Liste, Schlussbitte einmal je Gruppe |
| 3e-3 | `d8bd2f8` | LLM-Formulierung: Prompt-Template, `_pruefe_zahlen_konsistenz`, Fake-LLM-Tests |
| 3e-3 Nachb. a | `e8963f6` | Dopplung im Bericht behoben; Zuordnung per Regelname; Zahl-Kontrolle je Gruppe; Prompt-Update |
| 3e-3 Nachb. b | `be2534a` | Pflichtzahlen = gezeigte Zahlen (nur `f.title`); Diagnose in `_meta`; sauberer Rückfalltext |
| 3e-3d | `e25a184` | 7 Schutztests wiederhergestellt (Szenario 1–7) |
| 3e-3e | `4dd148f` | Vollständigkeit: Richtung (Haben/Soll + Konto) und Anzahl-Substantiv ("5 Konten", "6 Monatswerte"); Prompt auf 800 Zeichen; 13 neue Tests |
| 3e-3f | `f63bf69` | Pro-Gruppe-Aufruf, Sammelgruppe (>max_befunde), Timeout-Meldung, neue Schlusszeile; 5 neue Tests (563 gesamt) |

### Entscheidungen

- **`llm: optional`** im Frontmatter: Skill läuft mit `NullLlmClient` (deterministischer Fallback), kein Laufabbruch.
- **`status: experimental`**: standardmäßig deaktiviert; Schalter `llm.experimentelle_skills_aktiv: true` aktiviert ihn.
- **Pflichtzahlen = gezeigte Zahlen**: `_pflicht_zahlen_norm` und `_extrahiere_zahlen_norm` lesen nur `f.title`, da der Prompt dem Modell nur Titel zeigt, nicht Details.
- **Diagnose** (Rückfallgrund je Gruppe) geht in `SkillResult.meta["rueckfall_gruppen"]`, nicht in den Befundtext.
- **Bericht**: Experimentelle Findings erscheinen ausschließlich im Abschnitt „🤖 KI-gestützt", nicht in Fehler-/Auffälligkeits-/Hinweis-Zählern.
- **Pro-Gruppe-Aufruf** (3e-3f): Ein LLM-Aufruf je Gruppe (nicht alle auf einmal). `llm.max_befunde_je_gruppe` (Standard 3): Gruppen mit mehr Befunden → deterministisch („Sammelgruppe"), kein LLM-Aufruf. Timeout/Fehler einer Gruppe betrifft nur sie.
- **Schlusszeile** (3e-3f): „X von Y Gruppen; Z Sammelgruppen und N Rückfälle als Standardtext".

### Echtlauf August 2026 (Mistral)

Nach 3e-3b: **8 von 8 Gruppen LLM-formuliert, 0 Rückfälle.**
Vor Korrektur (3e-3 original): 2/8 LLM, 6/8 Rückfall (Ursache: `_pflicht_zahlen_norm` las `f.detail`).

Nach 3e-3f (Pro-Gruppe-Aufruf, max_befunde=3): **3/8 LLM, 2 Sammelgruppen, 3 Rückfälle; 7:32 min** (Apple Silicon, Mistral).
Sammelgruppen: `saldenrichtung` (5 Befunde), `vormonat-fortschreibung` (8 Befunde).
Rückfälle: `belege-abgleich`, `durchlaufende-posten`, `umsatz-beweis` (Zahlen-/Vollständigkeitsprüfung).

---

## Experimentelle Skills – Infrastruktur ✓

Aufgebaut im Rahmen von 3e (`e8963f6`):

| Komponente | Inhalt |
|---|---|
| `LlmConfig.experimentelle_skills_aktiv` | Schalter in `LlmConfig`, Standard `false`; in `config/lokal.example.yaml` und `config/default.yaml` dokumentiert |
| `SkillResult.experimentell`, `.deaktiviert` | Flags: von `run_one_skill()` im Runner gesetzt; beim SQLite-Roundtrip erhalten |
| Graph | `experimentelle_aktiv` wird in `create_graph()` und `run_pruefung()` aus `LokaleConfig` gelesen |
| Bericht | `overall_severity`, Zähler, Schweregrad-Blöcke und „Ohne Befund" schließen experimentelle Results aus; Fehler aktiver experimenteller Skills erscheinen in KI-gestützt |

---

## Schritt 3c – beleg-extraktion: Entscheidung experimentell ✓

Eval-Ergebnis (Mistral:latest, 12 Belege): LLM-Pipeline 61,1 % vs. Basis 66,7 %.
Stichprobe unter Mindestgröße (25 Belege). Qwen-Vergleich ausstehend (→ Offene Punkte f).
Kriterien für Beförderung zu `stable` stehen in `docs/PLAN_PHASE_3.md`.

---

## Schritt 3c – LLM-Skill `beleg-extraktion` ✓

Neue Pakete und Änderungen:

| Datei / Paket | Inhalt |
|---|---|
| `skills/beleg-extraktion/SKILL.md` | Frontmatter: `llm: true`, `runs_after: []`, `inputs: [context.belege]` |
| `skills/beleg-extraktion/check.py` | `run(ctx, llm)` – verarbeitet nur Belege mit `alle==[]` und `kind!="storno"`; Guard `_wert_in_text()` für DE/EN-Betragsformate, Ziffern-Fallback; Pydantic-Validierung mit `json.loads`-Fallback (E8); Modell aus `llm.modell_fuer("beleg-extraktion")` |
| `skills/beleg-extraktion/prompts/extraktion.md` | Prompt-Template mit `{{ belegtext }}`-Platzhalter, Daten-Delimiter gegen Injection |
| `skills/beleg-extraktion/tests/test_beleg_extraktion.py` | 32 Tests: Guard, Parse-Fallback, Fehlerfälle, Injection-Fixture, parametrisierte Betragsformate |
| `skills/beleg-extraktion/tests/fixtures/beleg_injection.txt` | Fixture mit Injection-Versuch für Guard-Test |
| `src/fibu/skills_runtime/runner.py` | Dispatch ausschließlich per `manifest.braucht_llm`-Flag (nicht per Signatur); `import inspect` entfernt |
| `src/fibu/llm/protocol.py` | `generiere()` erhält `*, modell: str = ""` (Protocol-Erweiterung) |
| `src/fibu/llm/null.py` | `generiere()` erhält `*, modell: str = ""` |
| `src/fibu/cli.py` | `fibu eval vorlage --ordner <Periodenordner>` – erzeugt JSON-Vorlage mit OCR-Texten; schreibt nach `EVAL_REAL_DIR` oder Periodenordner |
| `evals/run_eval.py` | Eval-Skript: liest `EVAL_REAL_DIR/vorlage_*.json`, ruft beleg-extraktion auf, gibt Trefferquote je Feld (betrag/datum/nummer) aus |

**Korrekturen aus 3b:** Dispatch per `braucht_llm`-Flag statt Signatur-Erkennung. `tests/unit/skills_runtime/test_runner_llm.py` angepasst.

32 neue Tests (skills/beleg-extraktion). 330 Tests grün.

---

## Schritt 3b – LLM-Integration in Skills-Runtime ✓

Neue Pakete und Änderungen:

| Datei / Paket | Inhalt |
|---|---|
| `src/fibu/skills_runtime/loader.py` | `SkillManifest` erhält Feld `braucht_llm: bool = False`; Frontmatter-Parser liest `llm: true/false` |
| `src/fibu/skills_runtime/runner.py` | `run_one_skill(manifest, ctx, llm)` – neuer optionaler Parameter `llm: LlmClient \| None = None`; Fallback-Finding (severity=„info") wenn `braucht_llm` und `isinstance(llm, NullLlmClient)` **vor** Modulimport; Signatur-Erkennung via `inspect.signature(run_fn)` – 2-Parameter-Funktion bekommt `llm` übergeben |
| `src/fibu/skills_runtime/__init__.py` | `run_skills(ctx, skills_dir, llm=None)` – neuer `llm`-Parameter; forwarded an `run_one_skill` |
| `src/fibu/graph/nodes.py` | Knoten `fuehre_skills_aus` nimmt `llm` aus Closure und übergibt an `run_skills()` |
| `src/fibu/graph/graph.py` | `create_graph(store, checkpointer, mail_sender, llm)` – neuer `llm`-Parameter; Closure einfängt `llm` |
| `src/fibu/graph/runner.py` | `run_pruefung(ordner, …, llm=None)` – lädt `OllamaClient` oder `NullLlmClient` aus `LokaleConfig` wenn `llm=None` |
| `src/fibu/cli.py` | `_cmd_pruefen_skills` instanziiert `LlmClient` aus Konfiguration vor `run_pruefung` |
| `src/fibu/llm/ollama.py` | `generiere()` erhält optionalen Keyword-Parameter `modell: str = ""` (überschreibt `self._config.modell` für diesen Aufruf) |

28 neue Tests (unit/skills_runtime, unit/llm). 298 Tests grün.

---

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

---

## Offene Punkte

**(a) ✓ rueckfrage-entwurf: Vollständigkeit erweitern** – erledigt (3e-3e)
`_pflicht_zahlen_norm` erkennt jetzt zusätzlich Anzahlen vor deutschem Substantiv
(`_ANZAHL_SUBST_RE`: `"5 Konten"`, `"6 Monatswerte"`). Neue Funktion `_pflicht_woerter()`
liefert `"Haben"`/`"Soll"` als Pflicht-Angabe, wenn sie im selben Titel wie eine
Kontonummer stehen. `_pruefe_gruppe()` prüft beides. Prompt auf 800 Zeichen erweitert.
13 neue Tests. Echtlauf (Ollama nicht erreichbar): 0/8 LLM, 8/8 deterministisch;
neue Muster greifen in Titeln von `vormonat-fortschreibung` und `saldenrichtung`.

**(b) rueckfrage-entwurf: Zahlenkontrolle prüft nur Ziffern**
Datumswerte (z. B. `14.08.2026`), Prozentzahlen und Kontonummern werden als
Ziffernfolgen verglichen, ohne Kontext. Falsch-Positive und -Negative möglich;
präzisere Muster für Datum und Konto prüfen.

**(c) eval: `run_eval.py` parst `Finding.detail`-Strings**
Extrahiert Betrag, Datum, Nummer durch String-Suche im Freitext statt strukturierte
Felder zu nutzen. Sobald `Finding.detail` stabilere Felder trägt, umstellen.

**(d) ✓ store: `_MIGRATIONS` fängt jeden `OperationalError`** – erledigt
`_MIGRATIONS` fängt jetzt nur noch `"duplicate column name"`-Fehler ab;
alle anderen `OperationalError`-Ausnahmen werden weitergegeben.

**(e) ✓ CLI: Konfigurationszeile nach stderr** – erledigt
Alle vier `print(f"Konfiguration: …")`-Aufrufe in `cli.py` schreiben auf `sys.stderr`.

**(f) beleg-extraktion: Qwen-Vergleich ausstehend**
Eval (12 Belege, Mistral): LLM-Pipeline 61,1 % vs. Basis 66,7 %. Qwen-Vergleich
offen; ggf. anderes Modell oder Prompt-Anpassung nötig bevor Beförderung zu `stable`.

**(g) Git-Tags gesetzt**
`phase-2-graph` und `stand-phase3-experimentell` (auf `b6d110f`) existieren.

**(h) Schritt 3e-4 weitgehend abgedeckt – prüfen und streichen**
Die in `docs/PLAN_3e.md` vorgesehene Testdatei `test_graph_rueckfrage_entwurf.py`
wurde nicht angelegt. Der Kern der Anforderung (*(experimentell)*-Label im Bericht,
Hinweis-Zähler unverändert bei eingeschaltetem Schalter) ist durch
`tests/integration/test_graph_pipeline.py::test_experimentell_findings_erhoehen_hinweis_zaehler_nicht`
und `tests/unit/test_report_experimentell.py` (16 Tests) abgedeckt.
Nicht abgedeckt: ein echter Graph-Lauf mit `experimentelle_skills_aktiv=True`, der
den `rueckfrage-entwurf`-Skill tatsächlich instanziiert (statt mockt). Schritt 3e-4
in PLAN_3e.md als weitgehend erledigt markieren; prüfen ob der fehlende End-to-End-Test
nachzutragen ist.

**(i) Phase 4: IMAP-Trigger und Ordner-Watcher**
Noch nicht begonnen. Einstiegspunkt: neues `Protocol IngestSource` in
`src/fibu/ingest/`; IMAP-Polling und Ordner-Watch als Implementierungen.

**(j) ✗ OCR-Zweitversuch geprüft und verworfen** – nicht übernommen (`6fd3cc1`, zurückgenommen in `1474586`)
Versuch: Für per OCR gelesene Belege ohne erkannten Betrag ein Zweitversuch mit 15 fest gereihten
Varianten (Graustufen, Autokontrast, Vergrößerung 2x/3x, Schwellwert 128; je `--psm 6/11/4`, `eng`),
eigener Cache je Variante, Belege mit Betrag bitgleich.
Messung 08 Aug (ohne Schalter): Belege ohne Betrag vorher 4, nachher 4 (3 Storno-Textdateien,
nicht OCR; 1 OCR-Beleg `YV/101_08_Park3.pdf`, erwartet 2,00 €). Befundzahlen 6/16/25 unverändert.
Begründung: Park3 ist in Punktmatrix-Schrift mit durchgestrichener Null gedruckt (Ziffern ca. 400 px
hoch bei 300 dpi). Keine der 15 Varianten liefert einen Betrag; auch Gegenproben außerhalb der Liste
(Verkleinerung 0,5x–0,15x, `deu`) nicht – bestenfalls `2.00e`, was bewusst nicht als Betrag gilt.
Kein Gewinn, aber 33 s Zusatzlaufzeit im Erstlauf (15 Tesseract-Läufe für einen Beleg).
Ergebnis: nicht übernommen; der Versuch bleibt in der Git-Historie sichtbar.
Mögliche Wege für solche Belege: Bild-Modell (über `src/fibu/llm/`, Ausgabe gegen Schema validiert)
oder andere OCR-Engine statt Tesseract, oder manuelle Erfassung (z. B. Eigenbeleg mit Betrag).
Hinweis: Im Cache `08 Aug/.fibu_cache` liegen aus dem Versuch noch 15 Variantendateien
`<sha>.<variante>.txt` für Park3; sie werden vom aktuellen Code nicht gelesen.

**(k) mypy: `src/fibu/contracts/finding.py:50` meldet unbenutztes `type: ignore`**
`mypy src` liefert auf diesem Rechner 1 Fehler (`unused-ignore`, schlägt `[prop-decorator]` statt
`[misc]` vor); bestand schon vor (j). Vermutlich unterschiedliche mypy-/Pydantic-Version zwischen
den Macs. Sperrdatei der Paketversionen erwägen (z. B. `uv.lock` einchecken), dann Kommentar anpassen.

**(l) Golden-Test und Gesamtvergleich laufen nur mit `FIBU_GOLDEN_DIR`**
Ohne die Variable überspringen sich `tests/golden/test_golden.py` und
`tests/integration/test_gesamtvergleich.py` (Teil der 19 übersprungenen Tests).
Vollständiger Lauf: `FIBU_GOLDEN_DIR="$HOME/fibu-echtdaten/08 Aug" pytest -q` – Basis 582 bestanden,
0 übersprungen.
