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

## Offen: CLI für die manuelle Prüfung

Der Legacy-Einstiegspunkt `python -m legacy.fibu_pruefer pruefen "<Ordner>"` bleibt
als Referenz erhalten. Eine neue CLI unter `python -m fibu pruefen` (die die neuen
Skills statt der Legacy-Checks aufruft) ist noch nicht implementiert. Sie entsteht
in Phase 2 (Schritt „Graph") nach Abschluss der Regelmigration.

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
