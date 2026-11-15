# Fortschritt Phase 1 – Fundament

## Schritt 2: Contracts (`src/fibu/contracts/`)

### Entstandene Module

| Datei | Öffentliche Typen |
|---|---|
| `finding.py` | `Ref`, `Calc`, `Finding` |
| `auswertung.py` | `Konto`, `WKonto`, `WGroup`, `OposItem`, `JahresEintrag`, `JahresKonto`, `Rueckfrage`, `UstvaKz`, `Auswertung` |
| `beleg.py` | `BelegRecord` |
| `entscheidung.py` | `Entscheidung` |
| `context.py` | `KlaerRow`, `ChangedKonto`, `Context` |

### `Finding` (Pydantic v2)

```python
class Finding(BaseModel):
    schema_version: str = "1"
    rule: str                              # Regel-ID, z. B. "bwa-rechenwege"
    severity: Literal["fehler", "pruefen", "info"]
    title: str
    detail: str
    calc: Calc | None = None               # erwartet, ist, differenz, formel
    refs: list[Ref] = []                   # art: "seite"|"konto"|"beleg", id, label
```

Unterschied zum Legacy-`Finding`: enthält `rule` (Regel-ID) und getypte `Calc`/`Ref`-Objekte statt freiem `ref: str`.

### `Context` (Pydantic v2)

```python
class Context(BaseModel):
    auswertung: Auswertung
    prev: Auswertung | None = None         # Vormonats-BWA
    belege: list[BelegRecord] = []
    klaerung: list[KlaerRow] = []
    changed_accounts: list[tuple[str, str, Decimal, Decimal]] = []
    config: dict[str, object] = {}
```

`changed_accounts` ist das typisierte Pendant zu `legacy.CheckResult.meta["changed"]`
(Kontonr, Name, ΔSoll, ΔHaben). Es wird von der Runtime nach `vormonat-fortschreibung`
befüllt und steht dann für `klaerungsliste` bereit.

### Wichtige Entscheidungen

**`Auswertung.page_texts: list[str]`** statt `pages: list[pdfwords.Page]`:
`pdfwords.Page` ist nicht serialisierbar. Der Rohtext je Seite reicht für alle
Checks außer `check_ustva`, das auf `page.lines` zugreift — das wird in Schritt 5
beim Skill `ustva-abgleich` gelöst.

**`ustva: dict[str, UstvaKz]`** mit `tax: Decimal | None = None` (nicht `Decimal = 0`):
Legacy-Checks testen `z81.get("tax") is not None`. Mit `None`-Default bleibt dieses
Muster semantisch erhalten.

**`bwa: dict[str, tuple[Decimal, Decimal]]`**: Pydantic v2 serialisiert Tuples als
JSON-Arrays und deserialisiert sie korrekt zurück; `dict[int, str]` (page_types)
bleibt Integer-gekeyt durch Pydantic-Coercion.

**Keine `from_legacy`/`to_legacy` in contracts**: Konvertierungsfunktionen kommen
erst in Schritt 5 (Thin-Wrapper-Phase), um die contracts-unabhängig und importierbar
zu halten.

**`schema_version: str = "1"`** auf `Auswertung`, `Finding`, `BelegRecord`,
`Entscheidung` — gemäß Zielarchitektur.

### Tests

32 Tests in `tests/unit/contracts/`: Felddvalidierung, ungültige Werte,
JSON-Roundtrip mit `Decimal`-Präzision, `dict[int, str]`-Schlüssel-Coercion,
optionale Felder (`betrag`, `calc`, `bwa_per`).

---

## Schritt 3: Skills-Runtime (`src/fibu/skills_runtime/`)

### Entstandene Module

| Datei | Zuständigkeit |
|---|---|
| `loader.py` | YAML-Frontmatter parsen, `SkillManifest`-Liste erzeugen |
| `scheduler.py` | Topologische Sortierung → Ausführungswellen |
| `runner.py` | Einzelnen Skill laden und ausführen, Fehler kapseln |
| `__init__.py` | `run_skills(ctx, skills_dir)` – öffentliche API |

### Öffentliche API

```python
# Einziger Einstiegspunkt für den Lauf
results: list[SkillResult] = run_skills(ctx, skills_dir=Path("skills"))

@dataclass
class SkillResult:
    skill_id: str
    findings: list[Finding]
    meta: dict[str, Any]   # z. B. changed_accounts nach vormonat-fortschreibung
    error: str | None      # Traceback wenn Skill abgestürzt ist
```

### Skill-Interface

Jedes `skills/<id>/check.py` implementiert:
```python
def run(ctx: Context) -> list[Finding]: ...
```

Das SKILL.md-Frontmatter steuert die Ausführungsreihenfolge:
```yaml
runs_after: [vormonat-fortschreibung, belege-abgleich]
inputs: [auswertung, belege, klaerung]
```

### Wichtige Entscheidungen

**`ThreadPoolExecutor`** für parallele Wellen: konsistent mit `belege.scan()`;
für CPU-gebundene Checks läuft Python wegen GIL faktisch seriell, aber LLM-Skills
in späteren Phasen sind I/O-gebunden und profitieren davon.

**Unbekannte `runs_after`-Einträge werden ignoriert**: ein Skill kann auf einen
optionalen Skill verweisen, der im konkreten Lauf nicht vorhanden ist, ohne
blockiert zu werden.

**Zirkuläre Abhängigkeiten** lösen `RuntimeWarning` aus und laufen in einer
gemeinsamen Welle — kein Absturz.

**Fehler in Skill-Code** erzeugen ein `Finding` mit `severity="fehler"` und
`title="Prüfung nicht durchgeführt"` und brechen den Gesamtlauf nicht ab.
`SkillResult.error` enthält den vollständigen Traceback.

**Skill-Module** werden unter eindeutigem Namen
`_skills_runtime_{skill_id}` importiert, um Namenskollisionen zu vermeiden.

### Tests

26 Tests in `tests/unit/skills_runtime/`: Frontmatter-Parsing, alphabetische
Sortierung, Topologie-Algorithmus (Kette, Diamant, unbekannte Deps, Zyklus),
Einzelskill-Lauf (Erfolg, Absturz, fehlendes check.py, fehlende run-Funktion),
Integrationsdurchlauf mit `run_skills`.

---

## Offene Punkte für Schritt 5 (Thin Wrapper)

1. **`Auswertung.from_legacy()` / `to_legacy()`** – Konvertierung zwischen
   Legacy-Dataclass und Pydantic-Modell; `to_legacy()` muss minimale `Page`-Objekte
   für `check_ustva` rekonstruieren (braucht Rohtext aus `page_texts`).

2. **`BelegRecord.from_legacy(beleg: Beleg)`** – Konvertierung aus `legacy.belege.Beleg`.

3. **`changed_accounts`-Befüllung in der Runtime**: nach Ausführung von
   `vormonat-fortschreibung` soll `ctx.changed_accounts` aus `result.meta` gesetzt
   werden, bevor `klaerungsliste` startet. Mechanismus noch nicht implementiert.

4. **`check_ustva` und `page_texts`**: Die Datumslogik in `check_ustva` liest
   `a.pages[0].lines` (pdfwords-Objekte). Im Skill `ustva-abgleich` wird das mit
   `ctx.auswertung.page_texts[0]` gelöst.

---

## Nächster Schritt: Golden-Test (Schritt 4)

Ziel: einen anonymisierten Fixture-Monat unter `tests/fixtures/` anlegen, den
Legacy-Code darauf laufen lassen und den Bericht unter `tests/golden/` speichern.
Dieser Bericht ist ab dann die Messlatte: jede Skill-Migration muss ihn bit-gleich
reproduzieren.

**Voraussetzung**: ein echter oder synthetisch erzeugter BWA-Auswertungssatz als PDF
(oder anonymisierter Text-Fixture), der alle Seiten enthält, die `parser.py` liest
(BWA, Wertenachweis, Summen & Salden, OPOS, UStVA, Entwicklungsübersicht).
