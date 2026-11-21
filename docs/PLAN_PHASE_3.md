# Plan Phase 3 – LLM-Skills (3b–3f)

**Stand:** 2026-11-16  
**Ausgangspunkt:** Phase 3a abgeschlossen (LLM-Adapter: `LlmClient`-Protocol, `OllamaClient`,
`NullLlmClient`, `LlmConfig`, `fibu llm pruefen`). 270 Tests grün.

---

## Ziele von Phase 3

LLM-Fähigkeiten systematisch in die Skills-Runtime und den Graphen einbetten, ohne die Kerninvariante
zu brechen: **Zahlen und Prüflogik bleiben deterministisches Python. LLMs lesen, ordnen zu und
formulieren. Ihre Ausgabe wird gegen ein Pydantic-Schema validiert.**

| Schritt | Kern-Ergebnis |
|---|---|
| 3b | Skills-Runtime kann `run(ctx, llm)` aufrufen; Fallback auf NullLlmClient |
| 3c | Erster LLM-Skill `rueckfrage-formulierung` (Rückfragen auf Basis von Findings) |
| 3d | Graph-Knoten `formuliere_rueckfragen` + State-Erweiterung |
| 3e | LLM-Skill `bericht-narrativ` + Integration in `report.py` |
| 3f | Eval-Framework für LLM-Skills (`evals/`, `fibu llm eval`) |

---

## Festgelegte Entscheidungen (gelten ab 3b verbindlich)

**E6 – LLM-Skill-Signatur**  
Ein Skill, der ein LLM benötigt, deklariert `llm: true` im SKILL.md-Frontmatter.
Seine `run`-Funktion hat die Signatur `run(ctx: Context, llm: LlmClient) -> list[Finding]`.
Skills ohne `llm: true` behalten die bisherige Signatur `run(ctx: Context) -> list[Finding]`.
Die Runtime erkennt die richtige Signatur über `inspect.signature`.

**E7 – Fallback bei fehlendem LLM**  
Wenn ein LLM-Skill ausgeführt wird und `NullLlmClient` oder kein Modell konfiguriert ist,
gibt der Skill ein einzelnes `Finding(severity="info", title="LLM nicht konfiguriert",
detail="Skill <id> benötigt ein LLM-Modell ...")` zurück. Kein Laufabbruch.
Der LLM-Fallback wird in `run_one_skill` **vor** dem Modulimport geprüft, damit der Import
nicht fehlschlägt, wenn das LLM fehlt.

**E8 – Pydantic-Validierung aller LLM-Antworten**  
Jeder LLM-Skill definiert ein lokales Pydantic-Modell `_LlmAntwort` und validiert die
JSON-Antwort des LLM damit (`_LlmAntwort.model_validate_json()`). Bei Validierungsfehler
oder `None`-Antwort gibt der Skill ein `Finding(severity="pruefen", ...)` aus und loggt
den rohen LLM-Output auf DEBUG-Ebene. Kein Skill propagiert eine Pydantic-Validierungsfehler-
Exception nach außen.

**E9 – Prompt-Templates als `.md`-Dateien**  
Prompts liegen unter `skills/<id>/prompts/<name>.md`, nicht inline im Python-Code.
Jedes Template enthält genau eine Jinja2-ähnliche `{{ variable }}`-Lücke pro dynamischem
Wert. Die Rendering-Logik steht in `check.py` (kein separates Template-Framework).
Die Variablen sind typisiert (Strings, keine Dezimalzahlen – Formatierung vor der Übergabe).

**E10 – Kein LLM-Output in Findings ohne Validierung**  
LLM-generierter Text darf nur in `Finding.detail` und `Finding.title` erscheinen,
nachdem er durch ein Pydantic-Modell validiert wurde. `Finding.calc` und `Finding.refs`
werden ausschließlich vom deterministischen Code gesetzt.

**E11 – Modell-Zuordnung pro Skill**  
`config/lokal.yaml` → `llm.modell_zuordnung` kann jedem Skill ein eigenes Modell zuweisen
(aus 3a). LLM-Skills rufen `llm.modell_fuer(skill_id)` auf und übergeben das Modell beim
Aufruf über eine `modell`-Option im Request-Body. `OllamaClient.generiere()` wird um einen
optionalen `modell`-Parameter erweitert, der den Standard aus `self._config.modell` überschreibt.

---

## Schritt 3b – LLM-Integration in Skills-Runtime

### Änderungen

| Datei | Änderung |
|---|---|
| `src/fibu/skills_runtime/loader.py` | `SkillManifest` erhält Feld `braucht_llm: bool = False`; Frontmatter-Parser liest `llm: true/false` |
| `src/fibu/skills_runtime/runner.py` | `run_one_skill(manifest, ctx, llm)` – neuer Parameter `llm: LlmClient`; `run_skills(ctx, skills_dir, llm)` analog; Signatur-Erkennung via `inspect.signature(run_fn)`; Fallback-Finding wenn `braucht_llm` und `isinstance(llm, NullLlmClient)` |
| `src/fibu/skills_runtime/__init__.py` | `run_skills`-Export: neuer `llm`-Parameter |
| `src/fibu/graph/nodes.py` | Knoten `fuehre_skills_aus` übergibt `llm` aus Closure an `run_skills()` |
| `src/fibu/graph/graph.py` | `create_graph(store, checkpointer, llm)` – neuer Parameter |
| `src/fibu/graph/runner.py` | `run_pruefung(ordner, mit_mail, llm)` lädt `LlmClient` aus Konfig |
| `src/fibu/cli.py` | Lädt `LlmClient` via `LokaleConfig.laden()` und `OllamaClient.aus_config()` oder `NullLlmClient()` je nach Konfiguration |
| `src/fibu/llm/ollama.py` | `generiere()` erhält optionalen Parameter `modell: str = ""` (überschreibt `self._config.modell`) |

### Teststrategie 3b

- `tests/unit/skills_runtime/test_runner_llm.py`:
  - `run_one_skill` mit `braucht_llm=False` → ruft `run(ctx)` auf (kein llm-Argument)
  - `run_one_skill` mit `braucht_llm=True` + echter `LlmClient`-Mock → ruft `run(ctx, llm)` auf
  - `run_one_skill` mit `braucht_llm=True` + `NullLlmClient` → gibt "LLM nicht konfiguriert"-Finding zurück, importiert Modul nicht
  - Bestehende Skills-Runtime-Tests bleiben unverändert grün (Backward-Compatibility)
- `tests/unit/llm/test_ollama_modell_param.py`:
  - `generiere()` mit `modell="llama3"` überschreibt `self._config.modell` im Request-Body

### Konfigurationsregeln 3b

```yaml
# config/lokal.example.yaml – Ergänzung
llm:
  modell: mistral          # Standard für alle LLM-Skills
  modell_zuordnung:
    rueckfrage-formulierung: mistral  # Skill-spezifisches Modell
    bericht-narrativ: llama3
```

---

## Schritt 3c – LLM-Skill `rueckfrage-formulierung`

### Ziel

Formuliert aus Findings mit `severity="fehler"` oder `severity="pruefen"` eine
menschenlesbare deutsche Rückfrage für den Steuerberater.
**Rechenweg und Betrag kommen aus `Finding.calc` (deterministisch) – das LLM formuliert
nur den Fließtext.**

### Neue Dateien

```
skills/rueckfrage-formulierung/
  SKILL.md
  check.py
  prompts/rueckfrage.md
  tests/
    test_rueckfrage_formulierung.py
    fixtures/
      findings_pruefen.json
      findings_leer.json
```

### SKILL.md-Frontmatter

```yaml
skill_id: rueckfrage-formulierung
beschreibung: Formuliert Rückfragen auf Basis von Findings (Severity fehler/pruefen).
llm: true
runs_after: []
inputs: [findings]
```

### Schema der LLM-Antwort

```python
class _LlmAntwort(BaseModel):
    text: str               # max. 300 Zeichen, Deutsch, kein Markdown
    adressat: Literal["steuerberater", "mandant"] = "steuerberater"
```

### Fallback ohne LLM

Wenn LLM fehlt: Finding `severity="info"`, `title="Rückfragen nicht formuliert"`,
`detail="Kein LLM konfiguriert – Rückfragen müssen manuell formuliert werden."`.

### Prompt-Template `prompts/rueckfrage.md`

```
Du bist ein Wirtschaftsprüfer-Assistent. Formuliere eine kurze, höfliche Rückfrage
auf Deutsch (maximal 300 Zeichen) für den Steuerberater zu folgendem Befund:

Regel: {{ regel }}
Titel: {{ titel }}
Detail: {{ detail }}
{% if rechnung %}Rechnung: {{ rechnung }}{% endif %}

Antworte ausschließlich als JSON mit den Feldern "text" und "adressat".
```

### Teststrategie 3c

- Positiv-Test: Mock-LLM gibt valide JSON-Antwort → Finding mit `severity="info"` und
  formuliertem Text
- Negativ-Test: Keine Findings mit `severity != "info"` → Skill gibt leere Liste zurück
- Fallback-Test: `NullLlmClient` → "LLM nicht konfiguriert"-Finding
- Validierungsfehler-Test: Mock-LLM gibt ungültiges JSON → `severity="pruefen"`, kein Crash
- Text-Längen-Test: LLM-Antwort `text` > 300 Zeichen → wird auf 300 abgeschnitten (Finding-Detail)

---

## Schritt 3d – Graph-Knoten `formuliere_rueckfragen`

### Ziel

Neuer Knoten im LangGraph zwischen `bewerte` und `erstelle_bericht`.
Führt den Skill `rueckfrage-formulierung` aus und speichert die Rückfragen im State/Store.

### Änderungen

| Datei | Änderung |
|---|---|
| `src/fibu/graph/state.py` | Neues optionales Feld `rueckfragen: list[Rueckfrage] = []` |
| `src/fibu/graph/nodes.py` | Neuer Knoten `formuliere_rueckfragen`: liest Findings aus Store, ruft Skill, schreibt Rueckfragen zurück |
| `src/fibu/graph/graph.py` | Kante `bewerte → formuliere_rueckfragen → erstelle_bericht` |
| `src/fibu/store/sqlite.py` | Neue Tabelle `rueckfragen` (lauf_id, finding_id, text, adressat); `speichere_rueckfragen()`, `lade_rueckfragen()` |
| `src/fibu/report.py` | Abschnitt „Rückfragen" am Ende des Berichts (nur wenn Liste nicht leer) |
| `src/fibu/contracts/entscheidung.py` | Bereits vorhanden; `Rueckfrage`-Modell aus `auswertung.py` wird genutzt |

### State-Änderung

```python
# state.py
rueckfragen: list[dict[str, str]] = []  # {"finding_id": ..., "text": ..., "adressat": ...}
```

### Teststrategie 3d

- Integration-Test: Graph-Lauf mit Mock-LLM → Bericht enthält „Rückfragen"-Abschnitt
- Integration-Test: Graph-Lauf ohne LLM → kein „Rückfragen"-Abschnitt (nur Info-Finding)
- Store-Test: `speichere_rueckfragen` / `lade_rueckfragen` Roundtrip
- Graph-Reihenfolge-Test: Knoten `formuliere_rueckfragen` wird nach `bewerte` und vor
  `erstelle_bericht` ausgeführt (via `state.lauf_id` in allen drei Knoten prüfbar)

---

## Schritt 3e – LLM-Skill `bericht-narrativ`

### Ziel

Erzeugt einen deutschen Einleitungs-Paragraphen und eine Kurzfassung (Executive Summary)
für den Prüfbericht. **Ohne LLM bleibt der Bericht strukturell unverändert (nur Tabellen).**

### Neue Dateien

```
skills/bericht-narrativ/
  SKILL.md
  check.py
  prompts/einleitung.md
  prompts/zusammenfassung.md
  tests/
    test_bericht_narrativ.py
```

### SKILL.md-Frontmatter

```yaml
skill_id: bericht-narrativ
beschreibung: Erzeugt Einleitung und Zusammenfassung für den Prüfbericht.
llm: true
runs_after: [rueckfrage-formulierung]
inputs: [auswertung, findings]
```

### Schema der LLM-Antwort

```python
class _LlmAntwort(BaseModel):
    einleitung: str    # 1–3 Sätze, max. 500 Zeichen, Deutsch
    zusammenfassung: str  # 2–5 Sätze, max. 800 Zeichen, Deutsch, keine Zahlen
```

### Invariante: Zahlen im Narrativ

Das LLM **empfängt keine Beträge** im Prompt. Es bekommt nur:
- Periode (z. B. „Oktober 2024")
- Anzahl Findings je Severity
- Liste der Skill-IDs mit Findings (keine Beträge)

Beträge erscheinen ausschließlich in den Tabellen des Berichts (deterministisch).

### Integration in `report.py`

```python
# report.py – neue Signaturen
def erstelle_markdown(findings, narrativ=None) -> str: ...
def erstelle_html(findings, narrativ=None) -> str: ...
```

Wenn `narrativ=None` (kein LLM): Bericht beginnt wie bisher ohne Einleitung.

### Teststrategie 3e

- Positiv-Test: Mock-LLM → Bericht enthält Einleitung und Zusammenfassung
- Negativ-Test: `NullLlmClient` → Bericht ohne Einleitung (kein Regressions-Test gegen
  Golden-Output nötig, da Narrativ nicht im Golden-JSON enthalten)
- Längen-Test: Einleitung > 500 Zeichen → wird gekürzt + Info-Log
- Zahlen-Injektions-Test: LLM gibt Text mit Betrag zurück (z. B. „12.345,67 €") →
  wird akzeptiert aber im Detail-Log markiert (kein Fehler, da formell valide)

---

## Schritt 3f – Eval-Framework

### Ziel

Messbare Qualitätssicherung für LLM-Skills:
- Pydantic-Validierungsrate pro Skill und Modell
- Regress-Erkennung bei Modellwechsel
- Offline-Ausführung (kein Netz nötig für Mock-Evals)

### Verzeichnisstruktur

```
evals/
  README.md
  rueckfrage-formulierung/
    eval_01_prueffall.yaml     # prompt + expected_keys + (optional) expected_text_contains
    eval_02_leerfall.yaml
  bericht-narrativ/
    eval_01_normallauf.yaml
```

### Eval-Datei-Format

```yaml
# evals/rueckfrage-formulierung/eval_01_prueffall.yaml
skill_id: rueckfrage-formulierung
beschreibung: Findings mit severity=pruefen → Rückfrage-Text vorhanden
input_findings:
  - rule: bwa-rechenwege
    severity: pruefen
    title: "Rechenweg-Differenz Konto 3860"
    detail: "Erwartet 1234, ist 1230"
expected_schema_valid: true
expected_findings_count: 1
expected_text_contains: ["Rückfrage", "Konto"]  # optional
```

### Neue Dateien

| Datei | Inhalt |
|---|---|
| `src/fibu/evals/runner.py` | `run_eval(eval_path, llm) -> EvalResult`; lädt YAML, baut Minimal-Context, ruft Skill, prüft Schema und expected-Felder |
| `src/fibu/evals/report.py` | `erstelle_eval_bericht(results) -> str` (Markdown-Tabelle) |
| `src/fibu/cli.py` | `fibu llm eval [--skill <id>] [--modell <modell>]`; liest alle `evals/**/*.yaml`, gibt Tabelle aus; Exit 1 wenn Validierungsrate < 90 % |

### Metriken

| Metrik | Schwellenwert | Quelle |
|---|---|---|
| Pydantic-Validierungsrate | ≥ 90 % | Pflicht, Exit 1 |
| Antwort-nicht-None-Rate | ≥ 80 % | Warnung |
| Textlänge im Rahmen | ≥ 95 % | Info |

### Teststrategie 3f

- `tests/unit/evals/test_runner.py`:
  - Eval mit Mock-LLM (100 % valide) → `EvalResult.validierungsrate == 1.0`
  - Eval mit Mock-LLM (None-Antwort) → Metrik korrekt
  - `fibu llm eval` Exit-Code 0 bei ≥ 90 %, Exit-Code 1 darunter
- `evals/`-Dateien selbst werden durch `pytest -q` **nicht** ausgeführt (kein Netz, kein Ollama
  im CI). Separater Aufruf via `fibu llm eval`.

---

## Entscheidung: beleg-extraktion bleibt experimentell (2026-11-21)

### Eval-Ergebnis (Mistral:latest, 12 geprüfte Belege, ∅ 29 s/Beleg)

| Feld    | Basis/Legacy | LLM-Pipeline |
|---------|-------------|--------------|
| Betrag  | 83,3 %      | 75,0 %       |
| Datum   | 50,0 %      | 58,3 %       |
| Nummer  | 66,7 %      | 50,0 %       |
| **Gesamt**  | **66,7 %**  | **61,1 %**   |

Betrag wird seit 2026-11-19 deterministisch gewählt (Regeln A/B/C), ist nicht mehr
vom LLM abhängig und landet deshalb in beiden Spalten auf demselben Wert.
Qwen-Vergleich steht noch aus.

### Begründung

Die LLM-Pipeline verbessert Datum gegenüber der Basis (+8,3 Pp.), verschlechtert
aber Nummer (−16,7 Pp.) und Betrag (−8,3 Pp.). Gesamt liegt sie 5,6 Pp. unter dem
Legacy-Parser. Die Kombination ist damit noch nicht „mindestens so gut wie Legacy
allein". Zudem liegt der Stichprobenumfang (12 Belege) deutlich unter dem
Mindest-Schwellenwert von 25 geprüften Belegen.

**Folge:** `beleg-extraktion` erhält `status: experimental` und ist standardmäßig
deaktiviert (`llm.experimentelle_skills_aktiv: false`). Der Skill läuft im Prüfbericht
nur, wenn der Schalter explizit gesetzt wird. Der Bericht kennzeichnet seinen
Abschnitt mit *(experimentell)*.

### Kriterien für Beförderung zu `stable`

Ein Upgrade von `experimental` auf `stable` ist freigegeben, wenn alle drei
Bedingungen gleichzeitig erfüllt sind:

1. **Stichprobe:** Mindestens 25 geprüfte Belege (geprueft=true in der Vorlage).
2. **Falsch-Anteil:** Höchstens 10 % je Feld (Betrag, Datum, Nummer).
3. **Netto-Nutzen:** Die Kombination (Basis + LLM für Felder, die die Basis leer
   lässt) erzielt eine Einsatzfall-Quote von mindestens dem Basis-Niveau (d. h.
   der Skill schadet nicht, wo die Basis bereits funktioniert).

---

## Risiken und Gegenmaßnahmen

| Risiko | Wahrscheinlichkeit | Gegenmaßnahme |
|---|---|---|
| Ollama Structured Output erzeugt trotzdem invalides JSON | mittel | `pruefe_structured_output()` aus 3a warnt vorab; Pydantic-Validierung in jedem Skill als zweite Linie |
| LLM fügt Beträge ins Narrativ ein (Halluzination) | niedrig | Prompt enthält keine Beträge (E10 + Invariante in 3e); Zahlen-Injektions-Test in 3e |
| Bestehende Skills-Tests brechen durch Runner-Umbau | mittel | Inspect-basierte Signatur-Erkennung (E6) hält Backward-Compatibility; alle 270 bestehenden Tests müssen nach 3b grün sein |
| Skill-Import schlägt fehl wegen fehlendem `llm`-Import | niedrig | Fallback-Check **vor** Modulimport in `run_one_skill` (E7) |
| Rückfragen im Bericht enthalten vertrauliche Firmendaten | niedrig | Beleginhalte sind Daten, keine Anweisungen (CLAUDE.md); Prompt-Template enthält keine Rohtexte aus Belegen |
| Eval-YAMLs mit anonymisierten Testdaten versehentlich echte Daten | niedrig | `evals/` liegt im Repo → `.gitignore`-Prüfung; nur Minimal-Findings in YAML (Kontonummern, keine Beträge) |
| Modellwechsel bricht Pydantic-Validierung (anderes Ausgabeformat) | hoch | Eval-Framework (3f) erkennt Regression; `fibu llm eval` im CI-Gate |

---

## Teststrategie (Gesamtüberblick Phase 3)

### Invarianten, die nach jedem Schritt gelten müssen

1. `pytest -q` → alle Tests grün (kein LLM nötig, `NullLlmClient` als Standard)
2. `python -m legacy.fibu_pruefer pruefen "<Ordner>"` → unverändert lauffähig
3. Golden-Test für Fixture-Periode → keine unbeabsichtigten Abweichungen
4. `ruff check . && mypy src` → keine Fehler

### Test-Ebenen

| Ebene | Was wird getestet | LLM-Abhängigkeit |
|---|---|---|
| Unit / contracts | Pydantic-Validierung, ID-Hashing | keine |
| Unit / llm | Protocol, OllamaClient (urllib-Mock), NullLlmClient | keine (mock) |
| Unit / skills_runtime | Loader, Runner, Scheduler, Signatur-Erkennung | keine (NullLlmClient) |
| Unit / skills | check.py je Skill (inkl. LLM-Skills mit Mock) | Mock (`unittest.mock`) |
| Integration / graph | Graph-Pipeline, Checkpointer, Store | NullLlmClient |
| Golden | End-to-End Fixture-Vergleich | NullLlmClient |
| Evals | Echte LLM-Qualität, Metriken | Ollama (manuell) |

### Mindest-Testanzahl je Schritt

| Schritt | Neue Tests (Ziel) | Erwartete Gesamtzahl |
|---|---|---|
| 3b | ≥ 15 | ≥ 285 |
| 3c | ≥ 10 | ≥ 295 |
| 3d | ≥ 12 | ≥ 307 |
| 3e | ≥ 10 | ≥ 317 |
| 3f | ≥ 8 | ≥ 325 |

---

## Konfigurationsregeln (Zusammenfassung)

```yaml
# config/lokal.example.yaml – vollständiger llm-Abschnitt nach Phase 3
llm:
  anbieter: ollama
  url: http://localhost:11434
  modell: mistral               # Standard-Modell; leer = kein LLM
  temperatur: 0.0
  timeout_sekunden: 120
  modell_zuordnung:
    rueckfrage-formulierung: mistral
    bericht-narrativ: llama3    # Größeres Modell für Narrativ
```

**Regeln:**
- `llm.modell` leer → `NullLlmClient` wird verwendet; alle LLM-Skills geben "info"-Findings zurück.
- `FIBU_LLM_MODELL` Umgebungsvariable überschreibt `llm.modell` (aus 3a).
- `llm.modell_zuordnung` Einträge überschreiben das Standard-Modell pro Skill-ID.
- Kein Modell darf im Repo hinterlegt werden (`config/default.yaml` enthält nur Platzhalter).
- `llm.temperatur` ist immer `0.0` (Reproduzierbarkeit); kein Skill darf höhere Temperatur anfordern.
- LLM-Aufrufe ausschließlich über `src/fibu/llm/`; kein Skill ruft `urllib` oder `requests` direkt auf.

---

## Definition of Done (Phase 3 gesamt)

1. Alle Tests grün, `ruff` und `mypy` ohne Fehler.
2. Golden-Test: Bericht für Fixture-Periode identisch mit Phase-2-Referenz
   (LLM-Teile erscheinen nur, wenn `FIBU_LLM_MODELL` gesetzt ist).
3. `fibu llm pruefen` zeigt Konfiguration, Erreichbarkeit und Structured-Output-Unterstützung.
4. `fibu llm eval` läuft durch und zeigt Validierungsrate ≥ 90 % (manuell mit echtem Ollama).
5. Jeder LLM-Skill hat `SKILL.md`, mindestens einen Positiv- und einen Negativ-Test
   sowie einen Fallback-Test ohne LLM.
6. Kein Skill enthält Beträge oder Dezimalzahlen im Prompt-Template.
