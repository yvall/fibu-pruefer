# Plan Schritt 3e – Skill `rueckfrage-entwurf`

**Stand:** 2026-11-21  
**Ausgangspunkt:** Phase 3c abgeschlossen (`beleg-extraktion`). 330 Tests grün.

---

## 1. Zweck

Der Skill `rueckfrage-entwurf` liest alle `Finding`-Objekte mit
`severity in ("fehler", "pruefen")` aus den vorausgegangenen Prüfskills und erzeugt daraus
einen Rückfragen-Entwurf an den Steuerberater. Die Fragen werden nach Themengruppen
(Skill-ID) gegliedert.

**Deterministische Basis** (ohne LLM, aber mit aktiviertem Schalter):  
Je Finding entsteht ein Absatz nach dem Muster:

> Zu [Thema]: [Titel] – bitte prüfen und den Sachverhalt mitteilen.

Zahlen, Beträge, Kontonummern und Datumsangaben werden dabei 1:1 aus dem
`Finding.title`/`Finding.detail`/`Finding.calc` übernommen; es findet keine
eigene Berechnung statt.

**LLM-Ergänzung** (wenn Modell konfiguriert und Schalter aktiv):  
Das Modell formuliert den Fließtext zwischen den eingesetzten Daten-Platzhaltern um
und fasst verwandte Rückfragen eines Themas zu einem Absatz zusammen.
Alle Zahlen, Beträge, Kontonummern und Datumsangaben erscheinen ausschließlich als
benannte Platzhalter im Prompt-Template (z. B. `{{ betrag_1 }}`), nie als Freitext.
Nach der Modellausgabe prüft `_pruefe_zahlen_konsistenz()` (siehe §3), dass keine
neuen Ziffernfolgen im Text auftauchen. Bei Verstoß → Rückfall auf deterministischen
Standardtext, kein Laufabbruch.

**Ausgabe:**  
Pro Themengruppe ein `Finding(severity="info", rule="rueckfrage-entwurf")`, dessen
`detail` den Entwurfstext enthält. Die Ergebnisaussage und der Exit-Code des Laufs
bleiben unverändert; der Skill erzeugt ausschließlich `severity="info"`-Findings.

---

## 2. Unabhängigkeit von `beleg-zuordnung` (3d)

```yaml
# SKILL.md
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
  - context.befunde        # neues Feld, s. §3 → Offene Frage 1
  - auswertung.periode
```

Der Skill liest keine Belege, keine Jahreskonten und nichts aus dem Beleg-Zuordnungs-
Skill (3d). Er benötigt ausschließlich die kumulierten `Finding`-Objekte aus den
Vorgängerskills sowie die Periodenangabe für die Anrede.

Die Findings aus `beleg-extraktion` (falls aktiv) fließen ebenfalls ein, da sie im
`ctx.befunde`-Pool landen – aber der Skill hat keine direkte `runs_after`-Abhängigkeit
davon und kann auch ohne sie sinnvoll arbeiten.

---

## 3. Harte Regeln

### Zahlen kommen deterministisch aus den Befunden

1. Vor dem Modellaufruf extrahiert `_extrahiere_daten(findings)` je Finding die
   Felder `title`, `detail` und `calc` und baut ein Dict
   `{ "betrag_1": "1.234,56 €", "konto_1": "1370", ... }`.
2. Der Prompt enthält nur diese benannten Platzhalter, keine Rohbeträge als Freitext.
3. Nach Rückgabe prüft `_pruefe_zahlen_konsistenz(text: str, quellzahlen: set[str]) -> bool`
   per Regex `r"\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?"` alle Ziffernfolgen im Text gegen
   `quellzahlen`. Eine Zahl, die nicht in den Quellen vorkommt → Rückfall.
4. Ergibt der Rückfall, dass der deterministische Text die Anforderungen erfüllt,
   wird er stillschweigend verwendet; ein `Finding(severity="info", title="Zahl-Kontrolle")`
   informiert im Debug-Log, kein separater Bericht-Eintrag.

### Prompt-Injection-Schutz

Belegbeschreibungen (`BelegRecord.text`) und Klärungslistenkommentare (`KlaerRow.kommentar`)
gelangen **nicht** in den Prompt. Der Skill arbeitet ausschließlich mit den bereits
validierten `Finding`-Feldern aus Python-Code.

### Kein Versand, keine Seiteneffekte

Der Skill schreibt keine Datei, öffnet keine Verbindung und ruft keine Mail-Funktion auf.
Der Rückfragen-Entwurf erscheint ausschließlich als `Finding` im Bericht.

### Pydantic-Validierung der LLM-Antwort (E8)

```python
class _LlmAntwort(BaseModel):
    gruppen: list[_Gruppe]

class _Gruppe(BaseModel):
    thema: str                # Skill-ID oder fachlicher Oberbegriff, max. 60 Zeichen
    text: str                 # Rückfragetext, max. 500 Zeichen, kein Markdown
```

Bei Validierungsfehler oder `None`-Antwort → deterministischer Fallback.

---

## 4. Zustand: `status: experimental`

### Aktivierungslogik (bereits in der Runtime implementiert)

| `experimentelle_skills_aktiv` | Modell konfiguriert | Verhalten |
|---|---|---|
| `false` (Standard) | egal | Skill deaktiviert; `SkillResult.deaktiviert=True`; Bericht: `*(experimentelle Skills deaktiviert)*` |
| `true` | nein | Skill läuft deterministisch (Fallback); `SkillResult.experimentell=True` |
| `true` | ja | Skill läuft mit LLM + Zahl-Kontrolle; `SkillResult.experimentell=True` |

Die Laufzeit-Logik (`run_one_skill` in `src/fibu/skills_runtime/runner.py`) behandelt
`status: experimental` und `experimentelle_skills_aktiv` bereits korrekt – kein Umbau
der Runtime nötig.

### Deterministische Fallback-Funktion

Die Funktion `_entwurf_deterministisch(findings: list[Finding]) -> list[Finding]` wird
neu in `skills/rueckfrage-entwurf/check.py` implementiert. Sie existiert **noch nicht**
in `klaerungsliste/check.py`: der Klärungslisten-Skill erzeugt strukturierte
Einzel-Findings über offene Posten, aber keine zusammenfassende Rückfrageliste für den
Steuerberater. Die neue Funktion übernimmt diese Rolle für *alle* Prüfskills.

```python
def _entwurf_deterministisch(findings: list[Finding]) -> list[Finding]:
    """Erzeugt pro Skill-Gruppe ein info-Finding mit Rückfragetext."""
    ...
```

---

## 5. Tests

### Golden-Test und Gesamtvergleich unverändert

`rueckfrage-entwurf` hat `status: experimental`. Da `llm.experimentelle_skills_aktiv`
im Testlauf standardmäßig `false` ist, erscheint der Skill nicht im Golden-Output.
Der Golden-Test und alle NullLlmClient-Tests bleiben unberührt.

### Test: Fake-LLM mit erfundener Zahl wird zurückgewiesen

```python
def test_zahl_injektion_fallback(make_context):
    """LLM gibt '99.999,00 €' zurück – kommt nicht aus den Findings."""
    # Fake-LLM gibt Antwort mit Zahl, die in keinem Finding vorkommt
    llm = FakeLlm(response={"gruppen": [{"thema": "bwa-rechenwege",
                                          "text": "Bitte prüfen (99.999,00 €)."}]})
    findings = [Finding(rule="bwa-rechenwege", severity="pruefen",
                        title="Differenz 1.234,56 €", detail="...")]
    ctx = make_context()
    ctx.befunde = findings
    result = run(ctx, llm)
    # Zahl-Kontrolle schlägt an → deterministischer Fallback
    assert "99.999" not in result[0].detail
    assert "1.234,56" in result[0].detail
```

### Test: Experimentell-Label im Bericht (Graph-Integrationstest)

```python
def test_experimentell_label_im_bericht(tmp_path, make_context):
    """Graph-Lauf mit experimentelle_skills_aktiv=True → Label erscheint."""
    config = LokaleConfig(llm=LlmConfig(experimentelle_skills_aktiv=True))
    # ... run_pruefung mit NullLlmClient und obiger Config
    assert "*(experimentell)*" in bericht_text
```

### Weitere Tests

| Test | Typ | Ergebnis |
|---|---|---|
| Keine pruefen/fehler-Findings vorhanden | Negativ | Leere Liste |
| Positiv mit Fake-LLM (gültige Zahlen) | Positiv | Entwurf im Detail-Feld |
| Pydantic-Validierungsfehler (ungültiges JSON) | Fallback | deterministischer Text, kein Crash |
| Deterministische Funktion: 3 Themengruppen → 3 Findings | Unit | Korrekte Gruppierung |

Mindestanzahl neue Tests: ≥ 12. Erwartete Gesamtzahl: ≥ 342.

---

## 6. Offene Fragen (max. 3)

**F1 – Wie erhält der Skill die Findings aus Vorgängerskills?**  
*Problem:* `Context` hat kein `befunde`-Feld; Skills erhalten nur `ctx: Context`.  
*Empfehlung:* `Context` erhält `befunde: list[Finding] = []` (analog zu `changed_accounts`,
das ebenfalls durch die Runtime nachträglich befüllt wird). Die Skills-Runtime befüllt
dieses Feld unmittelbar vor Aufruf eines Skills mit `inputs: [context.befunde]`, indem
sie alle bis dahin akkumulierten Findings aus den Vorgänger-SkillResults zusammenführt.
Damit ist kein neuer Mechanismus nötig, nur eine Contract-Erweiterung.

**F2 – Findings aus `beleg-extraktion` (experimental) einschließen?**  
*Problem:* `beleg-extraktion` ist ebenfalls experimental und standardmäßig deaktiviert.
Wenn beide Schalter aktiv sind, landen seine Findings im Pool; wenn nicht, fehlen sie.
*Empfehlung:* Ja, wer `experimentelle_skills_aktiv: true` setzt, bekommt alle
experimentellen Skills, einschließlich deren Findings im Rückfragen-Entwurf. Keine
Sonderbehandlung nötig – der Pool enthält einfach, was die Runtime geliefert hat.

**F3 – Prompt-Template: ein Aufruf pro Lauf oder ein Aufruf pro Themengruppe?**  
*Problem:* Ein einzelner Aufruf mit allen Gruppen ist günstiger (Latenz, Kosten),
birgt aber höheres Risiko für ein voluminöses, schwer zu validierendes Output.
*Empfehlung:* Ein Aufruf pro Lauf mit allen Gruppen auf einmal; `_LlmAntwort.gruppen`
ist eine Liste. Wenn die Pydantic-Validierung fehlschlägt, gilt der Rückfall für alle
Gruppen gemeinsam. Bei Bedarf kann später auf gruppenweise Aufrufe umgestellt werden.

---

## 7. Aufwand – einzeln committierbare Teilschritte

### Schritt 3e-1 – `Context.befunde` und Runtime-Befüllung

Dateien:
- `src/fibu/contracts/context.py`: Feld `befunde: list[Finding] = []` ergänzen
- `src/fibu/skills_runtime/runner.py`: Vor Aufruf eines Skills mit
  `inputs: [context.befunde]` den Pool befüllen
- Bestehende Tests anpassen (Roundtrip, Serialisierung)

Commit: `Kontext um Befunde-Feld erweitern für Rückfrage-Skill`

---

### Schritt 3e-2 – Deterministischer Kern (`check.py` ohne LLM)

Dateien:
- `skills/rueckfrage-entwurf/SKILL.md` (Frontmatter: `status: experimental`, `llm: true`,
  `runs_after: [klaerungsliste, ...]`, `inputs: [context.befunde, auswertung.periode]`)
- `skills/rueckfrage-entwurf/check.py`: `_entwurf_deterministisch()`, `run()` mit
  NullLlmClient-Fallback
- `skills/rueckfrage-entwurf/tests/test_rueckfrage_entwurf.py`:
  Positiv-, Negativ-, Fallback-Test

Commit: `Skill rueckfrage-entwurf: deterministischer Entwurf`

---

### Schritt 3e-3 – LLM-Formulierung mit Zahl-Kontrolle

Dateien:
- `skills/rueckfrage-entwurf/prompts/rueckfrage.md` (Prompt-Template mit
  Daten-Platzhaltern, kein Rohtext)
- `skills/rueckfrage-entwurf/check.py`: `_extrahiere_daten()`,
  `_pruefe_zahlen_konsistenz()`, LLM-Pfad in `run()`
- Tests: Zahl-Injektions-Test, Positiv mit Fake-LLM, Pydantic-Fehler-Fallback

Commit: `Skill rueckfrage-entwurf: LLM-Formulierung mit Zahl-Kontrolle`

---

### Schritt 3e-4 – Graph-Integrationstest und Bericht-Label

Dateien:
- `tests/integration/test_graph_rueckfrage_entwurf.py`: Graph-Lauf mit
  `experimentelle_skills_aktiv=True` + NullLlmClient → `*(experimentell)*` im Bericht

Commit: `Skill rueckfrage-entwurf: Graph-Integrationstest`
