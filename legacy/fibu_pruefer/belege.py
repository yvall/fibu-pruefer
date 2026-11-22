"""Beleg-Agent: liest Belege/Gutschriften aus dem Ordner und gleicht sie mit der Buchhaltung ab.

Die Unterordner (Kostenstellen wie CA/MA/YV/Allgemein) werden bewusst NICHT ausgewertet –
alle Dateien außer dem BWA-Ordner werden gleich behandelt.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps

from .checks import CheckResult, close, eur, pdate
from .parser import ZERO, Auswertung, OposItem
from .pdfwords import dec

AMT_DE = re.compile(r"(?<![\d.,])-?(\d{1,3}(?:\.\d{3})+|\d+),\d{2}(?!\d)")
AMT_EN = re.compile(r"(?<![\d.,])(\d{1,6}\.\d{2})(?=\s*(?:€|EUR|ELR|EUF|FUF|EURO))")
AMT_EN_PRE = re.compile(r"€\s*(\d{1,3}(?:,\d{3})*\.\d{2}|\d+\.\d{2})")
AMT_DASH = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+|\d+),-")
LEIST = re.compile(r"(?:Leistungszeitraum|Leistungsmonat|Abrechnungszeitraum|f[üu]r\s+Monat|Monat)\s*[:\s]\s*(?:(Januar|Februar|M[äa]rz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+(\d{4})|(\d{1,2})[./](\d{4}))", re.I)
MONTHS_DE = ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "dezember"]
DATE_ANY = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")
NUM_ID = re.compile(r"\b(?:\d{7,12}|[A-Z0-9]{2,}[-/][A-Z0-9\-/]{3,})\b")
BRUTTO_KEYS = re.compile(r"brutto|gesamt|rechnungsbetrag|endbetrag|zu zahlen|zahlbetrag|total|auszahlung|gutschriftsbetrag|summe|amount due", re.I)
NETTO_KEYS = re.compile(r"netto|net amount|zwischensumme|subtotal", re.I)
SUFFIXES = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
KLAERUNG_HINT = re.compile(r"kl[äa]rung|ungekl", re.I)


@dataclass
class Beleg:
    path: Path
    rel: str
    sha: str
    text: str = ""
    kind: str = "beleg"                  # gutschrift | rechnung | beleg
    brutto: list[Decimal] = field(default_factory=list)
    netto: list[Decimal] = field(default_factory=list)
    alle: list[Decimal] = field(default_factory=list)
    daten: list[str] = field(default_factory=list)
    nummern: list[str] = field(default_factory=list)
    leistung: tuple[int, int] | None = None
    ocr: bool = False
    ocr_variante: str | None = None      # gesetzt, wenn der OCR-Zweitversuch den Text geliefert hat

    @property
    def norm(self) -> str:
        return re.sub(r"[\s\-/]", "", self.text).upper().replace("O", "0")

    @property
    def primary(self) -> Decimal | None:
        return max(self.brutto) if self.brutto else None


def _read_text(p: Path) -> tuple[str, bool]:
    suf = p.suffix.lower()
    if suf in (".txt", ".md"):
        return p.read_text(errors="ignore"), False
    if suf == ".pdf":
        t = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout
        if len(t.strip()) > 20:
            return t, False
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["pdftoppm", "-r", "300", "-png", str(p), f"{td}/p"], capture_output=True)
            out = []
            for img in sorted(Path(td).glob("p*.png")):
                out.append(subprocess.run(["tesseract", str(img), "stdout", "--psm", "6", "-l", "eng"], capture_output=True, text=True).stdout)
            return "\n".join(out), True
    r = subprocess.run(["tesseract", str(p), "stdout", "--psm", "6", "-l", "eng"], capture_output=True, text=True)
    return r.stdout, True


def leistungsmonat(text: str) -> tuple[int, int] | None:
    m = LEIST.search(text)
    if not m:
        return None
    if m.group(1):
        name = m.group(1).lower().replace("maerz", "märz").replace("marz", "märz")
        return int(m.group(2)), MONTHS_DE.index(name) + 1 if name in MONTHS_DE else 0
    return int(m.group(4)), int(m.group(3))


def analyse(text: str) -> dict:
    alle, brutto, netto = [], [], []
    for line in text.splitlines():
        found = [dec(m.group(0)) for m in AMT_DE.finditer(line)]
        found += [Decimal(m.group(1)) for m in AMT_EN.finditer(line)]
        found += [Decimal(m.group(1).replace(",", "")) for m in AMT_EN_PRE.finditer(line)]
        found += [dec(m.group(1) + ",00") for m in AMT_DASH.finditer(line)]
        alle += found
        if found and BRUTTO_KEYS.search(line) and not NETTO_KEYS.search(line):
            brutto.append(found[-1])
        if found and NETTO_KEYS.search(line):
            netto.append(found[-1])
    head = text[:900]
    if re.search(r"Eigenbeleg|Ersatzbeleg|Fehlende\s+\w+\s+Rechnung", text, re.I):
        kind = "eigenbeleg"
        for m in re.finditer(r"^\s*\S.*?\s{2,}(\d{1,5})\s{2,}(\d{2})\s*$", text, re.M):   # "€ 12   Ct. 00"
            v = Decimal(f"{m.group(1)}.{m.group(2)}")
            alle.append(v)
            brutto.append(v)
    elif re.search(r"Gutschrift", head, re.I):
        kind = "gutschrift"
    elif not alle and re.search(r"cancel|storn|reversal", text, re.I):
        kind = "storno"
    elif re.search(r"rechnung|invoice|quittung|beleg|facture|receipt", text, re.I):
        kind = "rechnung"
    else:
        kind = "beleg"
    return dict(alle=alle, brutto=brutto or ([max(alle)] if alle else []), netto=netto, kind=kind,
                daten=DATE_ANY.findall(text), nummern=sorted(set(NUM_ID.findall(text))), leistung=leistungsmonat(text))


# ---------------------------------------------------------------------------------------------
# OCR-Zweitversuch: nur für per OCR gelesene Belege, in denen der erste Durchgang keinen Betrag fand.
# Feste Reihenfolge; es gewinnt die erste Variante, deren Text nach analyse() einen Betrag liefert.
# Belege mit erkanntem Betrag werden nie erneut gelesen (Ergebnis und Cache bleiben unverändert).

OCR_SCHWELLE = 128


def vv_grau(img: Image.Image) -> Image.Image:
    return img.convert("L")


def vv_autokontrast(img: Image.Image) -> Image.Image:
    return ImageOps.autocontrast(vv_grau(img))


def _vv_skaliert(faktor: int) -> Callable[[Image.Image], Image.Image]:
    def vv(img: Image.Image) -> Image.Image:
        g = vv_autokontrast(img)
        return g.resize((g.width * faktor, g.height * faktor), Image.Resampling.LANCZOS)
    return vv


vv_x2 = _vv_skaliert(2)
vv_x3 = _vv_skaliert(3)


def vv_schwelle(img: Image.Image) -> Image.Image:
    return vv_autokontrast(img).point(lambda v: 255 if v >= OCR_SCHWELLE else 0)


OCR_VORVERARBEITUNG: tuple[tuple[str, Callable[[Image.Image], Image.Image]], ...] = (
    ("grau", vv_grau),
    ("autokontrast", vv_autokontrast),
    ("x2", vv_x2),
    ("x3", vv_x3),
    ("schwelle", vv_schwelle),
)
OCR_PSM: tuple[str, ...] = ("6", "11", "4")


def ocr_varianten() -> list[tuple[str, Callable[[Image.Image], Image.Image], str]]:
    """Alle Varianten in fester Reihenfolge: je Vorverarbeitung die Seiteneinteilungen --psm 6, 11, 4."""
    return [(f"{name}-psm{psm}", vv, psm) for name, vv in OCR_VORVERARBEITUNG for psm in OCR_PSM]


def _ocr_bild(img: Image.Image, psm: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "v.png"
        img.save(f)
        return subprocess.run(["tesseract", str(f), "stdout", "--psm", psm, "-l", "eng"],
                              capture_output=True, text=True).stdout


def _bilder(p: Path) -> list[Image.Image]:
    if p.suffix.lower() == ".pdf":
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["pdftoppm", "-r", "300", "-png", str(p), f"{td}/p"], capture_output=True)
            out = []
            for f in sorted(Path(td).glob("p*.png")):
                with Image.open(f) as im:
                    im.load()
                    out.append(im.copy())
            return out
    with Image.open(p) as im:
        im.load()
        return [im.copy()]


def ocr_zweitversuch(p: Path, sha: str, cache: Path) -> tuple[str, str] | None:
    """Liefert (Variante, Text) der ersten Variante mit erkanntem Betrag, sonst None.
    Jede Variante hat einen eigenen Cache-Eintrag <sha>.<variante>.txt; <sha>.txt bleibt unberührt."""
    bilder: list[Image.Image] | None = None
    for variante, vv, psm in ocr_varianten():
        cf = cache / f"{sha}.{variante}.txt"
        if cf.exists():
            text = cf.read_text(encoding="utf-8")
        else:
            if bilder is None:
                bilder = _bilder(p)
            if not bilder:
                return None
            text = "\n".join(_ocr_bild(vv(b), psm) for b in bilder)
            cf.write_text(text, encoding="utf-8")
        if analyse(text)["alle"]:
            return variante, text
    return None


def _load_one(p: Path, rel: str, cache: Path) -> Beleg:
    sha = hashlib.sha1(p.read_bytes()).hexdigest()
    cf = cache / f"{sha}.txt"
    if cf.exists():
        raw = cf.read_text(encoding="utf-8")
        ocr, text = raw.startswith("#OCR\n"), raw.split("\n", 1)[1]
    else:
        text, ocr = _read_text(p)
        cf.write_text(("#OCR\n" if ocr else "#TXT\n") + text, encoding="utf-8")
    b = Beleg(p, rel, sha, text, ocr=ocr, **analyse(text))
    if ocr and not b.alle:
        treffer = ocr_zweitversuch(p, sha, cache)
        if treffer is not None:
            variante, text2 = treffer
            b = Beleg(p, rel, sha, text2, ocr=True, ocr_variante=variante, **analyse(text2))
    return b


def scan(period_dir: Path, bwa_dirname: str = "BWA") -> list[Beleg]:
    from concurrent.futures import ThreadPoolExecutor
    cache = period_dir / ".fibu_cache"
    cache.mkdir(exist_ok=True)
    jobs = []
    for p in sorted(period_dir.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in SUFFIXES or p.name.startswith("."):
            continue
        rel = p.relative_to(period_dir)
        if rel.parts[0].lower() == bwa_dirname.lower() or rel.parts[0].startswith(("Pruefbericht", ".", "__MACOSX")):
            continue
        jobs.append((p, str(rel)))
    with ThreadPoolExecutor(max_workers=4) as ex:
        return list(ex.map(lambda j: _load_one(j[0], j[1], cache), jobs))


def find_combos(target: Decimal, cands: list[tuple[Beleg, Decimal]], max_items: int = 8, limit: int = 3) -> list[list[tuple[Beleg, Decimal]]]:
    cands = sorted((c for c in cands if c[1] > 0), key=lambda c: -c[1])
    res: list[list[tuple[Beleg, Decimal]]] = []
    nodes = [0]
    suffix = [ZERO] * (len(cands) + 1)
    for i in range(len(cands) - 1, -1, -1):
        suffix[i] = suffix[i + 1] + cands[i][1]

    def dfs(i: int, rest: Decimal, cur: list):
        if len(res) >= limit or nodes[0] > 300_000:
            return
        nodes[0] += 1
        if abs(rest) <= Decimal("0.005") and cur:
            res.append(list(cur))
            return
        if i >= len(cands) or len(cur) >= max_items or rest < 0 or suffix[i] < rest - Decimal("0.005"):
            return
        c = cands[i]
        if c[1] <= rest + Decimal("0.005"):
            cur.append(c)
            dfs(i + 1, rest - c[1], cur)
            cur.pop()
        dfs(i + 1, rest, cur)

    dfs(0, target, [])
    return res


def booked_in_period(a: Auswertung) -> tuple[set[int], list[str]]:
    """Welche offenen Posten wurden im Berichtsmonat gebucht? Exakt über die Monatsbewegung je Personenkonto
    (Summe der Posten = Soll- bzw. Haben-Bewegung des Kontos); Rückfall auf das Rechnungsdatum."""
    idx: set[int] = set()
    notes: list[str] = []
    by: dict[str, list[int]] = {}
    for i, it in enumerate(a.opos):
        by.setdefault(it.konto, []).append(i)
    for konto, ids in by.items():
        k = a.sus.get(konto)
        deb = konto.startswith("1")
        target = (k.per_soll if deb else k.per_haben) if k else None
        vals = [(i, a.opos[i].soll if deb else a.opos[i].haben) for i in ids]
        found = None
        if target is not None and target > 0:
            from itertools import combinations
            for n in range(1, len(vals) + 1):
                hits = [c for c in combinations(vals, n) if abs(sum((v for _, v in c), ZERO) - target) <= Decimal("0.005")]
                if hits:
                    found = hits[0]
                    if len(hits) > 1:
                        notes.append(f"Konto {konto}: Zuordnung der Monatsbewegung zu Posten nicht eindeutig")
                    break
        if found is not None:
            idx |= {i for i, _ in found}
        elif target is None or target > 0:
            for i in ids:
                d = pdate(a.opos[i].datum)
                if d and (d.year, d.month) >= (a.year, a.month):
                    idx.add(i)
    return idx, notes


def check_belege(a: Auswertung, belege: list[Beleg]) -> CheckResult:
    r = CheckResult("belege", "Belege & Gutschriften ↔ Buchhaltung")
    if not belege:
        r.test(False, "pruefen", "Keine Belege im Ordner gefunden", "Unterhalb des Periodenordners (außer BWA) liegen keine PDF/Bild/Text-Dateien.")
        return r
    unreadable = [b for b in belege if not b.alle and b.kind != "storno"]
    for b in belege:
        if b.kind == "storno":
            r.test(False, "info", f"Stornobeleg ohne Betrag: {b.rel}", "Reine Stornierungs-/Erstattungsbestätigung (kein Zahlbetrag) – nur ablegen, keine Buchung nötig.", b.rel)
    for b in unreadable:
        r.test(False, "pruefen", f"Beleg nicht auswertbar: {b.rel}", "Kein Betrag erkannt (Scan-Qualität?). Manuell prüfen oder LLM-Extraktion aktivieren.", b.rel)

    # Dubletten
    by_sha: dict[str, list[Beleg]] = {}
    for b in belege:
        by_sha.setdefault(b.sha, []).append(b)
    for sha, bs in by_sha.items():
        if len(bs) > 1:
            r.test(False, "pruefen", "Identische Datei mehrfach abgelegt", ", ".join(x.rel for x in bs))
    by_key: dict[tuple, list[Beleg]] = {}
    for b in belege:
        for n in b.nummern:
            for amt in b.brutto[:1]:
                by_key.setdefault((n, amt), []).append(b)
    for (n, amt), bs in by_key.items():
        if len({x.sha for x in bs}) > 1:
            r.test(False, "pruefen", f"Belegnummer {n} mit {eur(amt)} in verschiedenen Dateien", ", ".join(x.rel for x in bs))

    # OPOS ↔ Belege
    def match(it: OposItem, amount: Decimal) -> tuple[Beleg | None, str]:
        nn = re.sub(r"[\s\-/]", "", it.belegnr).upper().replace("O", "0")
        if nn:
            for b in belege:
                if nn in b.norm:
                    return b, "nr"
        for b in belege:
            if any(close(amount, x, Decimal("0.005")) for x in b.brutto):
                return b, "betrag"
        return None, ""

    used: set[str] = set()
    in_period, _notes = booked_in_period(a)
    earlier = 0
    for i, it in enumerate(a.opos):
        if i not in in_period:
            earlier += 1
            continue                    # nicht im Berichtsmonat gebucht -> Beleg gehört in den Ordner des Buchungsmonats
        amount = it.soll if it.soll else it.haben
        b, how = match(it, amount)
        lab = f"{it.konto_name} {it.belegnr or '(ohne Nr.)'} {eur(amount)}"
        if b is None:
            r.test(False, "pruefen", f"Kein Beleg zu offenem Posten: {lab}",
                   "Weder Rechnungsnummer noch Betrag in den Belegen gefunden – Beleg fehlt, falsch benannt oder falscher Betrag gebucht.", f"Konto {it.konto}")
            continue
        used.add(b.sha)
        if how == "nr":
            ok = any(close(amount, x, Decimal("0.005")) for x in b.brutto + b.alle)
            r.test(ok, "fehler", f"Betrag weicht ab: {lab}",
                   f"Beleg {b.rel} enthält die Nummer, aber keinen Betrag {eur(amount)} (gefunden: {', '.join(eur(x) for x in b.brutto[:3])}).", f"Konto {it.konto}")
        else:
            r.test(True, "info", "", "")
            if not it.belegnr or b.kind == "eigenbeleg":
                continue
            r.test(False, "info", f"Beleg nur per Betrag zugeordnet: {lab}", f"{b.rel} – Rechnungsnummer {it.belegnr} im Beleg nicht gefunden.", f"Konto {it.konto}")

    if earlier:
        r.test(False, "info", f"{earlier} offene Posten stammen aus früheren Buchungsmonaten und wurden nicht gegen diesen Belegordner geprüft",
               "Ermittelt über die Monatsbewegung der Personenkonten; die Belege gehören in den jeweiligen Monatsordner.")
    # Rückfragen des Steuerberaters
    pool_all = [(b, b.primary) for b in belege if b.kind not in ("gutschrift", "storno") and b.primary]
    for q in a.rueckfragen:
        if q.betrag is None:
            continue
        # Kostenstellen-Kürzel im Text ("CA Erstattung …") nur als Suchfilter, nicht als Buchungslogik
        tok = (q.text.split() or [""])[0].upper()
        folder = [c for c in pool_all if c[0].rel.split("/")[0].upper() == tok]
        pool = folder or pool_all
        single = [c for c in pool if close(c[1], q.betrag, Decimal("0.005"))]
        if single:
            r.test(False, "info", f"Rückfrage {q.datum} {eur(q.betrag)} „{q.text}“: Einzelbeleg gefunden", "; ".join(c[0].rel for c in single[:3]))
            continue
        combos = find_combos(q.betrag, pool, max_items=6, limit=3)
        scope = f"Ordner {tok}" if folder else "alle Ordner"
        if combos and len(combos) == 1:
            lines = [" + ".join(f"{c[0].rel} ({eur(c[1])})" for c in combo) for combo in combos]
            r.test(False, "info", f"Rückfrage {q.datum} {eur(q.betrag)} „{q.text}“: eindeutige Aufschlüsselung gefunden",
                   f"Suche in {scope}: " + " || ".join(lines))
        else:
            sub = f" ({len(combos)}+ rechnerische Kombinationen – nicht eindeutig, daher keine Zuordnung)" if combos else ""
            r.test(False, "pruefen", f"Rückfrage {q.datum} {eur(q.betrag)} „{q.text}“: Aufschlüsselung nicht aus dem Belegordner belegbar{sub}",
                   f"Suche in {scope}. Die Belege zu diesem Betrag ({q.datum}) liegen offenbar nicht im Monatsordner – bitte Einzelbelege der Erstattung nachliefern/aufschlüsseln.")
    # Belege ohne Gegenstück
    rest = [b for b in belege if b.sha not in used and b.alle]
    if rest:
        r.test(False, "info", f"{len(rest)} Beleg(e) ohne Gegenstück in den offenen Posten",
               "Normal bei bereits bezahlten Rechnungen/Bankbelegen. Dateien: " + ", ".join(b.rel for b in rest[:15]) + (" …" if len(rest) > 15 else ""))
    return r


# ---------------------------------------------------------------------------------------------
# Klärungsliste (xlsx) – "Ungeklärte Posten"

@dataclass
class KlaerRow:
    text: str
    monat: str
    betrag: Decimal | None
    kommentar: str


def load_klaerung(period_dir: Path) -> list[KlaerRow]:
    rows: list[KlaerRow] = []
    try:
        import openpyxl
    except ImportError:
        return rows
    for p in sorted(period_dir.rglob("*.xlsx")):
        if p.name.startswith(("~", ".")) or not KLAERUNG_HINT.search(p.name):
            continue
        wb = openpyxl.load_workbook(p, data_only=True)
        for ws in wb:
            for i, r in enumerate(ws.iter_rows(values_only=True)):
                if i == 0 or not r or r[0] is None or str(r[0]).strip().lower().startswith("summe"):
                    continue
                v = r[2] if len(r) > 2 else None
                try:
                    amt = Decimal(str(round(float(v), 2))) if v is not None else None
                except (TypeError, ValueError):
                    amt = None
                mon = r[1].strftime("%m/%Y") if hasattr(r[1], "strftime") else (str(r[1]) if r[1] else "")
                rows.append(KlaerRow(str(r[0]).strip(), mon, amt, str(r[4]).strip() if len(r) > 4 and r[4] else ""))
    return rows


def check_klaerung(a: Auswertung, belege: list[Beleg], rows: list[KlaerRow], vormonat: CheckResult | None) -> CheckResult:
    r = CheckResult("klaerung", "Klärungsliste „Ungeklärte Posten“ ↔ Konto 1370 / Umbuchungen / Belege")
    if not rows:
        return r
    rowamts = [(x, x.betrag) for x in rows if x.betrag is not None and x.betrag > 0 and not x.text.lower().startswith(("101_", "\t"))]
    jk = next((j for j in a.jahreskonten if j.nr == "1370"), None)
    eps = Decimal("0.005")
    # 1) offene 1370-Posten ↔ Liste
    if jk:
        for e in jk.entries:
            amt = abs(e["soll"] - e["haben"])
            m = next((x for x, v in rowamts if abs(v - amt) <= eps), None)
            if m:
                r.test(False, "info", f"Konto 1370 {e['datum']} {eur(amt)} „{e['text'][:35]}“: in Klärungsliste geführt", f"Kommentar: {m.kommentar or '–'}", "Konto 1370")
            elif not e["text"].startswith("Deutsche Bank"):
                r.test(False, "pruefen", f"Konto 1370 {e['datum']} {eur(amt)} „{e['text'][:35]}“ fehlt in der Klärungsliste", "Posten offen, aber nicht in „Ungeklärte Posten“.", "Konto 1370")
    # 2) Liste ↔ Belege / Konto
    open_amts = [abs(e["soll"] - e["haben"]) for e in (jk.entries if jk else [])]
    for x, v in rowamts:
        beleg = next((b for b in belege if any(abs(v - y) <= eps for y in b.brutto)), None)
        still = any(abs(v - o) <= eps for o in open_amts)
        if beleg:
            r.test(False, "info", f"Klärung „{x.text[:40]}“ {eur(v)}: Beleg mit identischem Betrag gefunden", f"{beleg.rel} – bitte inhaltlich bestätigen; dann kann der Steuerberater den Posten umbuchen." + ("" if still else " Auf Konto 1370 nicht mehr offen."))
        elif not still:
            r.test(False, "info", f"Klärung „{x.text[:40]}“ {eur(v)}: nicht mehr auf Konto 1370 offen", "Vermutlich bereits umgebucht (siehe Umbuchungen unten) – Liste bereinigen.")
    # 3) Umbuchungen aus dem Vormonatsvergleich erklären
    if vormonat and vormonat.meta.get("changed"):
        for n, nm, dS, dH in vormonat.meta["changed"]:
            delta = dS - dH
            if abs(delta) < Decimal("1"):
                continue
            tgt = abs(delta)
            cands = [(x, v) for x, v in rowamts]
            hits = find_combos(tgt, [(x, v) for x, v in cands], max_items=4, limit=2)
            if hits:
                r.test(False, "info", f"Konto {n} {nm}: nachträgliche Änderung {eur(delta)} erklärbar",
                       "Entspricht Klärungsliste: " + " + ".join(f"{c[0].text[:30]} {eur(c[1])}" for c in hits[0]) + " (Umbuchung nach Klärung).", f"Konto {n}")
    # 4) negative Monatsbewegung auf 1370 ↔ Liste + Beleg
    k = a.sus.get("1370")
    if k and k.per_soll < 0:
        v = -k.per_soll
        x = next((x for x, y in rowamts if abs(y - v) <= eps), None)
        b = next((b for b in belege if any(abs(v - y) <= eps for y in b.brutto)), None)
        if x or b:
            r.test(False, "info", f"Konto 1370: Monatsbewegung −{eur(v)} nachvollziehbar",
                   f"Klärungsliste: {x.text if x else '–'} ({x.kommentar if x else ''}); Beleg: {b.rel if b else '–'}. Erledigter Klärungsposten wurde ausgebucht.", "Konto 1370")
    return r


def check_umsatz(a: Auswertung, belege: list[Beleg]) -> CheckResult:
    """Umsatzbeweis: Netto der Gutschriften/Rechnungen des Leistungsmonats ↔ Erlöskonten."""
    r = CheckResult("umsatz", "Umsatzerlöse ↔ Gutschriften des Leistungsmonats")
    erloes = sum((k.per_haben - k.per_soll for n, k in a.sus.items() if n.startswith("44") and len(n) == 4), ZERO)
    if erloes == 0:
        return r
    in_period, _n = booked_in_period(a)
    items = [it for i, it in enumerate(a.opos) if i in in_period and it.konto.startswith("1") and it.soll > 0]
    beweis, ersatz, nicht = [], [], []
    for it in items:
        d = pdate(it.datum)
        nn = re.sub(r"[\s\-/]", "", it.belegnr).upper().replace("O", "0")
        cands = [b for b in belege if (nn and nn in b.norm) or any(abs(it.soll - x) <= Decimal("0.005") for x in b.brutto)]
        g = next((b for b in cands if b.kind == "gutschrift"), None)
        e = next((b for b in cands if b.kind in ("eigenbeleg", "rechnung")), None)
        if g and g.leistung == (a.year, a.month):
            beweis.append((it, g))
        elif g and g.leistung is None:
            beweis.append((it, g))
        elif e and not g:
            ersatz.append((it, e))
        else:
            nicht.append(it)
    net = lambda b: (b.netto[-1] if b.netto else ZERO)
    s_b = sum((net(g) for _, g in beweis), ZERO)
    s_e = sum((net(e) for _, e in ersatz), ZERO)
    r.tests += 1
    for it, g in beweis:
        r.test(close(net(g) * Decimal("1.19"), it.soll, Decimal("0.05")), "fehler", f"Gutschrift {it.belegnr}: Netto × 1,19 ≠ gebuchter Betrag",
               f"Beleg netto {eur(net(g))}, gebucht brutto {eur(it.soll)}.", f"Konto {it.konto}")
    for it, e in ersatz:
        r.test(False, "pruefen", f"Umsatz {it.konto_name} {it.belegnr} ({eur(net(e))} netto) nur durch Ersatz-/Eigenbeleg gestützt",
               f"{e.rel} ist kein Originalbeleg des Kunden (Gutschrift/Rechnung) – Original nachfordern. "
               f"Hinweis im Beleg: {(e.text.strip().splitlines() or [''])[-1][:120]}", f"Konto {it.konto}")
    for it in nicht:
        r.test(False, "fehler", f"Umsatz {it.konto_name} {it.belegnr} {eur(it.soll)} ohne Beleg", "Weder Gutschrift noch Eigenbeleg im Ordner gefunden.", f"Konto {it.konto}")
    total = s_b + s_e
    r.test(close(total, erloes, Decimal("0.05")), "fehler", f"Umsatz {a.month:02d}/{a.year}: Belege ≠ Erlöskonten",
           f"Netto laut Gutschriften des Leistungsmonats {eur(s_b)} + Ersatzbelege {eur(s_e)} = {eur(total)}, Erlöskonten 44xx {eur(erloes)} (Differenz {eur(erloes - total)}).", "Konten 44xx")
    if close(total, erloes, Decimal("0.05")):
        r.meta["umsatz_ok"] = f"Umsatz {eur(erloes)} vollständig durch Gutschriften ({eur(s_b)}) und Ersatzbelege ({eur(s_e)}) belegt"
    return r


EXCL_NO_BELEG = {"6855", "6000", "6026", "6027", "6072", "6110", "6120", "6220", "6222", "6260", "6310", "7600", "7610"}


def check_deckung(a: Auswertung, belege: list[Beleg]) -> CheckResult:
    """Grobabgleich auf Summenebene: gebuchte Belegkosten (netto + Vorsteuer) ↔ Summe der Eingangsbelege."""
    r = CheckResult("deckung", "Kosten-Belegdeckung (Summenebene)")
    net = sum((k.per_soll - k.per_haben for n, k in a.sus.items() if len(n) == 4 and n[0] in "67" and n not in EXCL_NO_BELEG), ZERO)
    vst = sum((a.sus[n].per_soll for n in ("1401", "1406") if n in a.sus), ZERO)
    booked = net + vst
    docs = [b for b in belege if b.kind in ("rechnung", "beleg", "eigenbeleg") and b.primary and not b.rel.startswith("Allgemein/Ungekl")]
    # Umsatz-Ersatzbelege (Hays etc.) gehören nicht zu den Kosten
    docs = [b for b in docs if not (b.kind == "eigenbeleg" and b.netto and b.netto[-1] > 5000)]
    got = sum((b.primary for b in docs), ZERO)
    unread = [b.rel for b in belege if not b.alle and b.kind != "storno"]
    diff = booked - got
    ok = abs(diff) <= max(Decimal("5"), booked * Decimal("0.02"))
    r.test(ok, "pruefen", f"Gebuchte Kosten ≠ Summe der Eingangsbelege (Differenz {eur(diff)})",
           f"Gebucht {eur(net)} netto + {eur(vst)} Vorsteuer = {eur(booked)}; Eingangsbelege im Ordner {eur(got)} ({len(docs)} Dokumente). "
           f"{'Mehr gebucht als belegt' if diff > 0 else 'Mehr Belege als Buchungen'} – mögliche Ursachen: nicht lesbare Belege ({', '.join(unread) or 'keine'}), "
           f"Belege aus Vormonaten, Sammelbuchungen, Beleg ohne Buchung. Ausgenommen: Löhne, Sozialabgaben, AfA, Miete, Ertragsteuern.", "Summenebene")
    r.meta.update(booked=booked, belege=got)
    return r
