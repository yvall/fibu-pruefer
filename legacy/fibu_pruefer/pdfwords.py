"""PDF -> Seiten -> Zeilen -> Wörter mit Koordinaten.

Text-PDFs werden mit pdfplumber gelesen (exakt). Seiten ohne Textebene
(Scans) werden per Tesseract-OCR gelesen und als `ocr=True` markiert, damit
der Bericht diese Werte als weniger verlässlich kennzeichnen kann.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pdfplumber

AMT_RE = re.compile(r"^-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}$")
DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
MONTH_RE = re.compile(r"^[A-Z][a-z]{2}/\d{4}$")


def dec(s: str) -> Decimal:
    """'1.234,56' -> Decimal('1234.56')"""
    return Decimal(s.replace(".", "").replace(",", "."))


def is_amt(s: str) -> bool:
    return bool(AMT_RE.match(s))


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float


@dataclass
class Line:
    words: list[Word]
    top: float

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class Page:
    no: int
    lines: list[Line] = field(default_factory=list)
    ocr: bool = False

    @property
    def text(self) -> str:
        return "\n".join(l.text for l in self.lines)

    def head(self, n: int = 8) -> str:
        return " ".join(l.text for l in self.lines[:n])


def _group_lines(words: list[Word], tol: float = 3.0) -> list[Line]:
    words = sorted(words, key=lambda w: (w.top, w.x0))
    lines: list[Line] = []
    for w in words:
        if lines and abs(lines[-1].top - w.top) <= tol:
            lines[-1].words.append(w)
        else:
            lines.append(Line([w], w.top))
    for l in lines:
        l.words.sort(key=lambda w: w.x0)
    return lines


def _ocr_words(pdf_path: Path, page_no: int, width_pt: float) -> list[Word]:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "p"
        subprocess.run(
            ["pdftoppm", "-r", "300", "-f", str(page_no), "-l", str(page_no), "-png", str(pdf_path), str(base)],
            check=True, capture_output=True,
        )
        img = next(Path(td).glob("p*.png"))
        from PIL import Image  # pillow ist mit pdfplumber installiert
        with Image.open(img) as im:
            img_w = im.width
        res = subprocess.run(
            ["tesseract", str(img), "stdout", "--psm", "6", "-l", "eng", "tsv"],
            check=True, capture_output=True, text=True,
        )
    rows = [r.split("\t") for r in res.stdout.splitlines()[1:]]
    rows = [r for r in rows if len(r) == 12 and r[11].strip() and r[11].strip() not in ("|", "||", "_", "=", "—")]
    if not rows:
        return []
    scale = width_pt / img_w
    out = []
    for r in rows:
        x0 = int(r[6]) * scale
        x1 = (int(r[6]) + int(r[8])) * scale
        top = int(r[7]) * scale
        out.append(Word(_fix_ocr_token(r[11].strip()), x0, x1, top))
    return _merge_ocr_amounts(out)


def _fix_ocr_token(t: str) -> str:
    t = t.replace("\u2014", "-").replace("\u2013", "-")
    if re.fullmatch(r"-?\d+\.\d{2}", t):          # 4192.46 -> 4192,46
        t = t.replace(".", ",")
    return t


def _merge_ocr_amounts(words: list[Word]) -> list[Word]:
    """Zerrissene OCR-Beträge ('43.804 24', '12.267 ,84', '49 276,00') wieder zusammensetzen."""
    words = sorted(words, key=lambda w: (round(w.top / 4), w.x0))
    out: list[Word] = []
    i = 0
    while i < len(words):
        w = words[i]
        n = words[i + 1] if i + 1 < len(words) else None
        if n and abs(n.top - w.top) < 4 and 0 <= n.x0 - w.x1 < 5:
            if re.fullmatch(r"-?\d[\d.]*\d", w.text) and re.fullmatch(r",\d{2}", n.text):
                out.append(Word(w.text + n.text, w.x0, n.x1, w.top)); i += 2; continue
            if re.fullmatch(r"-?\d{1,3}\.\d{3}", w.text) and re.fullmatch(r"\d{2}", n.text):
                out.append(Word(w.text + "," + n.text, w.x0, n.x1, w.top)); i += 2; continue
            if re.fullmatch(r"-?\d{1,3}", w.text) and re.fullmatch(r"\d{3},\d{2}", n.text):
                out.append(Word(w.text + "." + n.text, w.x0, n.x1, w.top)); i += 2; continue
            if re.fullmatch(r"-?\d{1,3}", w.text) and re.fullmatch(r"\d{2}", n.text) and False:
                pass
        out.append(w)
        i += 1
    return out


def load_pages(pdf_path: str | Path, ocr: bool = True) -> list[Page]:
    pdf_path = Path(pdf_path)
    pages: list[Page] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, pg in enumerate(pdf.pages, start=1):
            raw = pg.extract_words(x_tolerance=1.5, y_tolerance=2)
            words = [Word(w["text"], w["x0"], w["x1"], w["top"]) for w in raw]
            used_ocr = False
            if not words and ocr:
                try:
                    words = _ocr_words(pdf_path, i, float(pg.width))
                    used_ocr = bool(words)
                except Exception:
                    words = []
            pages.append(Page(i, _group_lines(words), used_ocr))
    return pages


def classify(page: Page) -> str:
    h = page.head(10)
    if "Wertenachweis" in h:
        return "wertenachweis"
    if "Kurzfristige Erfolgsrechnung" in h:
        return "bwa"
    if "Vorjahresvergleich" in h:
        return "vorjahr"
    if "Entwicklungs" in h:
        return "entwicklung"
    if "Summen und Salden" in h:
        return "sus"
    if "OPOS" in h or "Rechnungs-Nr" in h:
        return "opos"
    if "Werte zur Datenübermittlung" in h or "Werte zur Datenubermittlung" in h:
        return "ustva_werte"
    if "Datenübermittlungsprotokoll" in h or "Datenubermittlungsprotokoll" in h:
        return "ustva_protokoll"
    if "Jahreskonto" in h:
        return "jahreskonto"
    if "UStVA" in page.text and "BWA" in page.text:
        return "letter"
    return "unknown"


def split_amount_suffix(words: list[Word]) -> list[tuple[Word, str | None]]:
    """Betragswörter samt direkt anhängendem S/H-Kennzeichen."""
    out = []
    for i, w in enumerate(words):
        if not is_amt(w.text):
            continue
        suf = None
        if i + 1 < len(words) and words[i + 1].text in ("S", "H") and words[i + 1].x0 - w.x1 < 8:
            suf = words[i + 1].text
        out.append((w, suf))
    return out


def cluster_ends(values: list[float], gap: float = 25.0) -> list[float]:
    """Spaltenpositionen (rechte Kante) per Lückenclustering."""
    vs = sorted(values)
    if not vs:
        return []
    groups = [[vs[0]]]
    for v in vs[1:]:
        if v - groups[-1][-1] > gap:
            groups.append([v])
        else:
            groups[-1].append(v)
    return [sum(g) / len(g) for g in groups]


def nearest(cols: list[float], x: float) -> int:
    return min(range(len(cols)), key=lambda i: abs(cols[i] - x))
