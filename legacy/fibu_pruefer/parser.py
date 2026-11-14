"""Parser für den DATEV-Auswertungssatz des Steuerberaters (Kanzlei-Rechnungswesen).

Liest: BWA, Wertenachweis, Entwicklungsübersicht, Summen & Salden, OPOS,
UStVA-Protokoll/-Werte, Jahreskonto sowie die Rückfragen im Anschreiben.
Alles Zahlenmaterial wird als Decimal geführt (S = +, H = -  bei Salden).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .pdfwords import (DATE_RE, MONTH_RE, Page, classify, cluster_ends, dec,
                       is_amt, load_pages, nearest, split_amount_suffix)

ZERO = Decimal("0")
MONTHS = {"Jan": 1, "Feb": 2, "Mrz": 3, "Mär": 3, "Apr": 4, "Mai": 5, "Jun": 6,
          "Jul": 7, "Aug": 8, "Sep": 9, "Okt": 10, "Nov": 11, "Dez": 12}
MONTH_NAMES = {"Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6, "Juli": 7,
               "August": 8, "September": 9, "Oktober": 10, "November": 11, "Dezember": 12}


@dataclass
class Konto:
    nr: str
    name: str
    eb: Decimal = ZERO          # Soll positiv
    per_soll: Decimal = ZERO
    per_haben: Decimal = ZERO
    ytd_soll: Decimal = ZERO
    ytd_haben: Decimal = ZERO
    saldo: Decimal = ZERO       # Soll positiv

    @property
    def per_move(self) -> Decimal:
        return self.per_soll - self.per_haben

    @property
    def ytd_move(self) -> Decimal:
        return self.ytd_soll - self.ytd_haben


@dataclass
class WGroup:
    zeile: str
    name: str
    bwa_per: Decimal | None = None
    bwa_ytd: Decimal | None = None
    kontos: list[dict] = field(default_factory=list)  # nr, sh, name, per, ytd
    ocr: bool = False


@dataclass
class OposItem:
    konto: str
    konto_name: str
    belegnr: str
    datum: str
    faellig: str
    gegenkonto: str
    soll: Decimal
    haben: Decimal
    text: str


@dataclass
class JahresKonto:
    nr: str
    name: str
    entries: list[dict] = field(default_factory=list)
    eb: Decimal = ZERO
    saldo: Decimal = ZERO       # Soll positiv
    jvz_soll: Decimal = ZERO
    jvz_haben: Decimal = ZERO


@dataclass
class Rueckfrage:
    datum: str
    betrag: Decimal | None
    text: str


@dataclass
class Auswertung:
    source: Path
    year: int = 0
    month: int = 0
    created: str = ""
    pages: list[Page] = field(default_factory=list)
    page_types: dict[int, str] = field(default_factory=dict)
    bwa: dict[str, tuple[Decimal, Decimal]] = field(default_factory=dict)       # Label -> (Monat, kumuliert)
    wgroups: list[WGroup] = field(default_factory=list)
    sus: dict[str, Konto] = field(default_factory=dict)
    sus_total: dict[str, Decimal] = field(default_factory=dict)
    opos: list[OposItem] = field(default_factory=list)
    opos_totals: dict[str, Decimal] = field(default_factory=dict)
    entwicklung: dict[str, list[Decimal]] = field(default_factory=dict)
    entw_months: list[str] = field(default_factory=list)
    ustva: dict[str, dict] = field(default_factory=dict)     # Kz -> {base, tax}
    ustva_zahllast: Decimal | None = None
    ustva_datum: str = ""
    jahreskonten: list[JahresKonto] = field(default_factory=list)
    rueckfragen: list[Rueckfrage] = field(default_factory=list)
    letter_amount: Decimal | None = None
    ocr_pages: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- BWA

def _bwa_cols(page: Page) -> tuple[float, float]:
    xs = []
    for l in page.lines[:8]:
        for w in l.words:
            if MONTH_RE.match(w.text):
                xs.append(w.x1)
    if not xs:
        raise ValueError("BWA-Spaltenköpfe nicht gefunden")
    return min(xs), max(xs)


def parse_bwa(page: Page) -> dict[str, tuple[Decimal, Decimal]]:
    c_per, c_ytd = _bwa_cols(page)
    out: dict[str, tuple[Decimal, Decimal]] = {}
    for l in page.lines:
        amts = [w for w in l.words if is_amt(w.text)]
        if not amts:
            continue
        label = " ".join(w.text for w in l.words if not is_amt(w.text)).strip()
        per = ytd = None
        for w in amts:
            if abs(w.x1 - c_per) <= 6:
                per = dec(w.text)
            elif abs(w.x1 - c_ytd) <= 6:
                ytd = dec(w.text)
        if label and (per is not None or ytd is not None):
            out[label] = (per if per is not None else ZERO, ytd if ytd is not None else ZERO)
    return out


# ------------------------------------------------------------------ Wertenachweis

def parse_wertenachweis(pages: list[Page]) -> list[WGroup]:
    amt_ends = [w.x1 for p in pages for l in p.lines for w in l.words if is_amt(w.text)]
    cols = cluster_ends(amt_ends, gap=20)
    if len(cols) != 4:
        # Fallback: nur Reihenfolge nutzen
        cols = []
    groups: list[WGroup] = []
    cur: WGroup | None = None
    for p in pages:
        for l in p.lines:
            ws = l.words
            if not ws or not re.fullmatch(r"\d{4}", ws[0].text):
                continue
            # Kopfzeilen überspringen
            second_is_sh = len(ws) > 1 and ws[1].text in ("S", "H")
            amts = [(w, None) for w in ws if is_amt(w.text)]
            if not amts:
                continue
            idx = None
            for i, w in enumerate(ws[:-1]):
                if re.fullmatch(r"\d{4,5}", w.text) and ws[i + 1].text in ("S", "H") and (i == 0 or not is_amt(ws[i - 1].text)):
                    idx = i
                    break
            if second_is_sh:
                if cur is None:
                    continue
                zeile_line = False
            else:
                zeile_line = True
                name_words = []
                for w in ws[1:]:
                    if re.fullmatch(r"\d{4,5}", w.text) or is_amt(w.text):
                        break
                    name_words.append(w.text)
                if idx is None:
                    # Formelzeile ("1051 Gesamtleistung  1020 Umsatzerlöse 1 ...") -> keine Konten
                    cur = None
                    continue
                cur = WGroup(ws[0].text, " ".join(name_words), ocr=p.ocr)
                groups.append(cur)
            k = idx if idx is not None else 0
            nr, sh = ws[k].text, ws[k + 1].text
            kname = []
            for w in ws[k + 2:]:
                if is_amt(w.text) or re.fullmatch(r"\d", w.text):
                    break
                kname.append(w.text)
            vals = [(w, dec(w.text)) for w in ws[k + 2:] if is_amt(w.text)]
            slots: dict[int, Decimal] = {}
            if cols:
                for w, v in vals:
                    slots[nearest(cols, w.x1)] = v
            else:
                nums = [v for _, v in vals]
                slots = dict(enumerate(nums))
            per, ytd = slots.get(0, ZERO), slots.get(2, ZERO)
            if cur is None:
                continue
            if 1 in slots and zeile_line:
                cur.bwa_per = slots[1]
            if 3 in slots and zeile_line:
                cur.bwa_ytd = slots[3]
            if 1 in slots and not zeile_line:
                cur.bwa_per = slots[1]
            if 3 in slots and not zeile_line:
                cur.bwa_ytd = slots[3]
            cur.kontos.append({"nr": nr, "sh": sh, "name": " ".join(kname), "per": per, "ytd": ytd})
    return groups


# ----------------------------------------------------------------- Summen & Salden

def parse_sus(pages: list[Page]) -> tuple[dict[str, Konto], dict[str, Decimal], list[str]]:
    warn: list[str] = []
    rows = []
    for p in pages:
        for l in p.lines:
            ws = l.words
            if not ws:
                continue
            first = ws[0].text
            if first in ("Summe",) or first.startswith("Summe"):
                if "Sachkonten" in l.text:
                    rows.append((l, "TOTAL"))
                continue
            if re.fullmatch(r"\d{3,5}", first) and any(is_amt(w.text) for w in ws):
                rows.append((l, "KONTO"))
    ends = []
    for l, kind in rows:
        for w, suf in split_amount_suffix(l.words):
            ends.append(w.x1 + (0 if suf is None else 0))
    cols = cluster_ends(ends, gap=25)
    if len(cols) != 6:
        warn.append(f"Summen/Salden: {len(cols)} statt 6 Spalten erkannt – Werte unsicher")
    konten: dict[str, Konto] = {}
    totals: dict[str, Decimal] = {}
    names = ["eb", "per_soll", "per_haben", "ytd_soll", "ytd_haben", "saldo"]
    for l, kind in rows:
        ws = l.words
        vals: dict[str, Decimal] = {}
        for w, suf in split_amount_suffix(ws):
            if len(cols) < 6:
                continue
            key = names[nearest(cols, w.x1)]
            v = dec(w.text)
            if key in ("eb", "saldo") and suf == "H":
                v = -v
            vals[key] = v
        if kind == "TOTAL":
            totals = {k: v for k, v in vals.items()}
            continue
        nr = ws[0].text
        name = " ".join(w.text for w in ws[1:] if not is_amt(w.text) and w.text not in ("S", "H"))
        konten[nr] = Konto(nr, name, vals.get("eb", ZERO), vals.get("per_soll", ZERO), vals.get("per_haben", ZERO),
                           vals.get("ytd_soll", ZERO), vals.get("ytd_haben", ZERO), vals.get("saldo", ZERO))
    return konten, totals, warn


# ---------------------------------------------------------------------------- OPOS

def parse_opos(pages: list[Page]) -> tuple[list[OposItem], dict[str, Decimal]]:
    items: list[OposItem] = []
    totals: dict[str, Decimal] = {}
    cur_nr, cur_name = "", ""
    for p in pages:
        # Spaltenposition Soll/Haben
        soll_x = haben_x = None
        for l in p.lines[:10]:
            if "Rechnungs-Nr" in l.text or ("Betrag" in l.text and "Soll" in l.text):
                for w in l.words:
                    if w.text == "Soll":
                        soll_x = w.x1
                    if w.text == "Haben":
                        haben_x = w.x1
        if soll_x is None or haben_x is None:
            soll_x, haben_x = 0.0, 1e9
        for l in p.lines:
            ws = l.words
            if not ws:
                continue
            txt = l.text
            if "**Gesamt**" in txt:
                amts = [dec(w.text) for w in ws if is_amt(w.text)]
                if amts and cur_nr:
                    totals[cur_nr] = amts[-1] if "H" not in [w.text for w in ws] else -amts[-1]
                    # Saldo als Soll-Betrag: S -> +, H -> -
                    sh = [w.text for w in ws if w.text in ("S", "H")]
                    totals[cur_nr] = amts[-1] * (-1 if sh and sh[0] == "H" else 1)
                continue
            date_idx = [i for i, w in enumerate(ws) if DATE_RE.match(w.text)]
            if len(date_idx) < 2:
                continue
            i0 = date_idx[0]
            if re.fullmatch(r"\d{5}", ws[0].text):
                cur_nr = ws[0].text
                cur_name = " ".join(w.text for w in ws[1:max(1, i0 - 1)])
            has_konto = bool(re.fullmatch(r"\d{5}", ws[0].text))
            belegnr = ws[i0 - 1].text if i0 >= (2 if has_konto else 1) else ""
            soll = haben = ZERO
            text_start = None
            gk = ""
            for i, w in enumerate(ws):
                if i > date_idx[1] and re.fullmatch(r"\d{4,5}", w.text) and not gk:
                    gk = w.text
            for w, suf in split_amount_suffix(ws):
                if suf:
                    # Saldo -> danach Tage / Buchungstext
                    j = ws.index(w)
                    text_start = j + 2
                    continue
                v = dec(w.text)
                if abs(w.x1 - soll_x) <= abs(w.x1 - haben_x):
                    soll += v
                else:
                    haben += v
            text = ""
            if text_start is not None:
                rest = ws[text_start:]
                if rest and re.fullmatch(r"-?\d+", rest[0].text):
                    rest = rest[1:]
                text = " ".join(w.text for w in rest)
            items.append(OposItem(cur_nr, cur_name, belegnr, ws[date_idx[0]].text, ws[date_idx[1]].text, gk,
                                  soll, haben, text))
    return items, totals


# --------------------------------------------------------------- Entwicklung (13 Mon.)

def parse_entwicklung(pages: list[Page]) -> tuple[list[str], dict[str, list[Decimal]]]:
    months: list[str] = []
    rows: dict[str, list[Decimal]] = {}
    for p in pages:
        for l in p.lines:
            ms = [w.text for w in l.words if MONTH_RE.match(w.text)]
            if len(ms) >= 12 and not months:
                months = ms
                continue
            amts = [w for w in l.words if is_amt(w.text)]
            if len(amts) == 13:
                label = " ".join(w.text for w in l.words if not is_amt(w.text)).strip()
                rows[label] = [dec(w.text) for w in amts]
    return months, rows


def month_labels(year: int, month: int, n: int) -> list[str]:
    names = {v: k for k, v in MONTHS.items() if k != "Mär"}
    out = []
    y, m = year, month
    for _ in range(n):
        out.append(f"{names[m]}/{y}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return out[::-1]


def normalize_labels(rows: dict[str, list[Decimal]], known: list[str]) -> dict[str, list[Decimal]]:
    """OCR-Labels ('Umsatzerlése') auf die exakten BWA-Zeilennamen abbilden."""
    import difflib
    out: dict[str, list[Decimal]] = {}
    for lab, vals in rows.items():
        clean = re.sub(r"\s+\d+$", "", lab)
        if clean in known:
            out[clean] = vals
            continue
        m = difflib.get_close_matches(clean, known, n=1, cutoff=0.7)
        out[m[0] if m else clean] = vals
    return out


# --------------------------------------------------------------------------- UStVA

def parse_ustva(pages_w: list[Page], pages_p: list[Page]) -> tuple[dict[str, dict], Decimal | None, str]:
    kz: dict[str, dict] = {}
    zahl = None
    datum = ""
    for p in pages_w:
        for l in p.lines:
            t = l.text
            m = re.search(r"Kz\.?\s*(\d+)\s+(.*)$", t)
            if m:
                nums = re.findall(r"-?\d[\d.]*(?:,\d{2})?", m.group(2))
                base = tax = None
                for n in nums:
                    if "," in n:
                        tax = dec(n)
                    else:
                        base = Decimal(n.replace(".", ""))
                kz[m.group(1)] = {"base": base, "tax": tax}
            if t.startswith("Verbleibender Betrag"):
                a = [w.text for w in l.words if is_amt(w.text)]
                if a:
                    zahl = dec(a[-1])
            m = re.search(r"erfolgt am:\s*(\d{2}\.\d{2}\.\d{4})", t)
            if m:
                datum = m.group(1)
    for p in pages_p:
        for l in p.lines:
            m = re.search(r"erfolgt am:\s*(\d{2}\.\d{2}\.\d{4})", l.text)
            if m:
                datum = m.group(1)
            if "Kz. 83" in l.text or "Kz.83" in l.text:
                a = [w.text for w in l.words if is_amt(w.text)]
                if a:
                    kz.setdefault("83_protokoll", {"base": None, "tax": dec(a[-1])})
    return kz, zahl, datum


# --------------------------------------------------------------------- Jahreskonto

def parse_jahreskonto(page: Page) -> JahresKonto | None:
    jk: JahresKonto | None = None
    soll_x = haben_x = None
    for i, l in enumerate(page.lines):
        t = l.text
        m = re.match(r"Konto\s+(\d{4,5})\s+(.*?)(?:\s+Funktion)?$", t)
        if m and jk is None:
            jk = JahresKonto(m.group(1), m.group(2))
            continue
        if "Umsatz" in t and "Soll" in t and "Haben" in t:
            for w in l.words:
                if w.text == "Soll":
                    soll_x = w.x1
                if w.text == "Haben":
                    haben_x = w.x1
        if jk is None:
            continue
        if l.words and DATE_RE.match(l.words[0].text) and soll_x:
            ws = l.words
            vals = [(w, dec(w.text)) for w in ws if is_amt(w.text)]
            soll = haben = ZERO
            for w, v in vals:
                if abs(w.x1 - soll_x) <= abs(w.x1 - haben_x):
                    soll += v
                else:
                    haben += v
            gk = ws[1].text if len(ws) > 1 and re.fullmatch(r"\d{4,5}", ws[1].text) else ""
            txt = " ".join(w.text for w in ws[2:] if not is_amt(w.text))
            jk.entries.append({"datum": ws[0].text, "gegenkonto": gk, "text": txt, "soll": soll, "haben": haben})
        if "EB-Wert" in t and "Saldo" in t and i + 1 < len(page.lines):
            nxt = page.lines[i + 1]
            parts = split_amount_suffix(nxt.words)
            nums = []
            for w, suf in parts:
                v = dec(w.text)
                nums.append(-v if suf == "H" else v)
            if len(nums) >= 4:
                jk.eb, jk.saldo, jk.jvz_soll, jk.jvz_haben = nums[0], nums[1], abs(nums[2]), abs(nums[3])
    return jk


# --------------------------------------------------------------------------- Brief

def parse_rueckfragen(text: str) -> list[Rueckfrage]:
    out: list[Rueckfrage] = []
    for ln in text.splitlines():
        m = re.search(r"(\d{2}[./]\d{2}[./]\d{4})\D{0,6}?([\d.]+,\d{2})\s*\S?\s*(?:[-–]\s*)?(.+)", ln)
        if m:
            out.append(Rueckfrage(m.group(1), dec(m.group(2)), m.group(3).strip()))
        elif re.search(r"Aufschl\w+", ln):
            out.append(Rueckfrage("", None, ln.strip(" •-")))
        elif re.search(r"Kontenpflege", ln):
            out.append(Rueckfrage("", None, ln.strip(" •-")))
    return out


# -------------------------------------------------------------------------- Haupt

def load_auswertung(pdf: str | Path) -> Auswertung:
    pdf = Path(pdf)
    pages = load_pages(pdf)
    a = Auswertung(pdf, pages=pages)
    a.ocr_pages = [p.no for p in pages if p.ocr]
    for p in pages:
        a.page_types[p.no] = classify(p)

    # Periode aus Titel
    for p in pages:
        m = re.search(r"Erfolgsrechnung\s+([A-Za-zäöüÄÖÜ]+)\s+(\d{4})", p.head(6))
        if m and m.group(1) in MONTH_NAMES:
            a.month, a.year = MONTH_NAMES[m.group(1)], int(m.group(2))
            break
    m = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", pages[1].head(2)) if len(pages) > 1 else None
    a.created = m.group(1) if m else ""

    by = lambda t: [p for p in pages if a.page_types[p.no] == t]
    try:
        for p in by("bwa"):
            a.bwa.update(parse_bwa(p))
    except Exception as e:  # noqa: BLE001
        a.warnings.append(f"BWA-Seite nicht lesbar: {e}")
    a.wgroups = parse_wertenachweis(by("wertenachweis")) if by("wertenachweis") else []
    if by("sus"):
        a.sus, a.sus_total, w = parse_sus(by("sus"))
        a.warnings += w
    if by("opos"):
        a.opos, a.opos_totals = parse_opos(by("opos"))
    if by("entwicklung"):
        _, raw = parse_entwicklung(by("entwicklung"))
        a.entw_months = month_labels(a.year, a.month, 13)
        a.entwicklung = normalize_labels(raw, list(a.bwa))
    a.ustva, a.ustva_zahllast, a.ustva_datum = parse_ustva(by("ustva_werte"), by("ustva_protokoll"))
    for p in by("jahreskonto"):
        jk = parse_jahreskonto(p)
        if jk:
            a.jahreskonten.append(jk)
    letter = pages[0].text
    if letter:
        a.rueckfragen = parse_rueckfragen(letter)
        m = re.search(r"in H[öo]he von\s+([\d.]+,\d{2})", letter)
        if m:
            a.letter_amount = dec(m.group(1))
    if a.ocr_pages:
        a.warnings.append("OCR verwendet auf Seite(n) " + ", ".join(map(str, a.ocr_pages)) +
                          " – dort gelesene Werte bitte stichprobenartig gegenprüfen")
    return a
