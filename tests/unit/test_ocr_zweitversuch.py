"""OCR-Zweitversuch im Beleg-Parser (legacy/fibu_pruefer/belege.py).

Nur synthetische Bilder und gemockte OCR; keine echten Belege.
Jede Vorverarbeitung und jede Seiteneinteilung hat einen Test, dessen gefälschte OCR
nur auf ein Merkmal genau dieser Variante antwortet – ohne die Variante wird er rot.
"""
from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageDraw, ImageFont

from legacy.fibu_pruefer import belege  # type: ignore[import]

BETRAG_TEXT = "Summe 12.34 €"
W, H = 40, 20


def _bild_mit_verlauf(pfad: Path) -> Path:
    """RGB-Bild mit flachem Grauverlauf 100..150 (kein voller Kontrast, keine reinen Schwarz/Weiß-Werte)."""
    img = Image.new("RGB", (W, H))
    for x in range(W):
        v = 100 + round(50 * x / (W - 1))
        for y in range(H):
            img.putpixel((x, y), (v, v, v))
    img.save(pfad)
    return pfad


def _periode(tmp_path: Path, erster_text: str = "unlesbar") -> tuple[Path, Path, str]:
    """Periodenordner mit einem Bildbeleg und vorbelegtem Erst-Cache (#OCR)."""
    periode = tmp_path / "08 Aug"
    (periode / "YV").mkdir(parents=True)
    bild = _bild_mit_verlauf(periode / "YV" / "beleg.png")
    import hashlib
    sha = hashlib.sha1(bild.read_bytes()).hexdigest()
    cache = periode / ".fibu_cache"
    cache.mkdir()
    (cache / f"{sha}.txt").write_text("#OCR\n" + erster_text, encoding="utf-8")
    return periode, cache, sha


def _werte(img: Image.Image) -> set[int]:
    """Vorkommende Grauwerte eines L-Bildes (leer für andere Modi)."""
    if img.mode != "L":
        return set()
    return {v for v, n in enumerate(img.histogram()) if n}


def _fake_ocr(bedingung: Any) -> Any:
    aufrufe: list[tuple[str, str, tuple[int, int]]] = []

    def ocr(img: Image.Image, psm: str) -> str:
        aufrufe.append((img.mode, psm, img.size))
        return BETRAG_TEXT if bedingung(img, psm) else "nichts lesbar"

    ocr.aufrufe = aufrufe  # type: ignore[attr-defined]
    return ocr


def _scan_einzeln(periode: Path) -> Any:
    bs = belege.scan(periode)
    assert len(bs) == 1
    return bs[0]


# --- je Vorverarbeitung ein Test -------------------------------------------------------------

def test_vorverarbeitung_grau(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    periode, _, _ = _periode(tmp_path)
    monkeypatch.setattr(belege, "_ocr_bild", _fake_ocr(lambda img, psm: img.mode == "L"))
    b = _scan_einzeln(periode)
    assert b.ocr_variante == "grau-psm6"
    assert b.alle == [Decimal("12.34")]


def test_vorverarbeitung_autokontrast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    periode, _, _ = _periode(tmp_path)

    def bed(img: Image.Image, psm: str) -> bool:
        werte = _werte(img)
        return img.size == (W, H) and bool(werte) and min(werte) == 0 and max(werte) == 255 and len(werte) > 2

    monkeypatch.setattr(belege, "_ocr_bild", _fake_ocr(bed))
    b = _scan_einzeln(periode)
    assert b.ocr_variante == "autokontrast-psm6"


def test_vorverarbeitung_vergroesserung_2x(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    periode, _, _ = _periode(tmp_path)
    monkeypatch.setattr(belege, "_ocr_bild", _fake_ocr(lambda img, psm: img.size == (2 * W, 2 * H)))
    b = _scan_einzeln(periode)
    assert b.ocr_variante == "x2-psm6"


def test_vorverarbeitung_vergroesserung_3x(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    periode, _, _ = _periode(tmp_path)
    monkeypatch.setattr(belege, "_ocr_bild", _fake_ocr(lambda img, psm: img.size == (3 * W, 3 * H)))
    b = _scan_einzeln(periode)
    assert b.ocr_variante == "x3-psm6"


def test_vorverarbeitung_schwellwert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    periode, _, _ = _periode(tmp_path)
    monkeypatch.setattr(belege, "_ocr_bild",
                        _fake_ocr(lambda img, psm: _werte(img) == {0, 255}))
    b = _scan_einzeln(periode)
    assert b.ocr_variante == "schwelle-psm6"


def test_seiteneinteilung_psm11(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    periode, _, _ = _periode(tmp_path)
    monkeypatch.setattr(belege, "_ocr_bild", _fake_ocr(lambda img, psm: psm == "11"))
    b = _scan_einzeln(periode)
    assert b.ocr_variante == "grau-psm11"


def test_seiteneinteilung_psm4(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    periode, _, _ = _periode(tmp_path)
    monkeypatch.setattr(belege, "_ocr_bild", _fake_ocr(lambda img, psm: psm == "4"))
    b = _scan_einzeln(periode)
    assert b.ocr_variante == "grau-psm4"


# --- Eigenschaften der Vorverarbeitungen -----------------------------------------------------

def test_vorverarbeitungen_wirken(tmp_path: Path) -> None:
    img = Image.open(_bild_mit_verlauf(tmp_path / "v.png"))
    assert belege.vv_grau(img).mode == "L"
    ak = _werte(belege.vv_autokontrast(img))
    assert min(ak) == 0 and max(ak) == 255
    assert belege.vv_x2(img).size == (2 * W, 2 * H)
    assert belege.vv_x3(img).size == (3 * W, 3 * H)
    assert _werte(belege.vv_schwelle(img)) == {0, 255}


def test_variantenreihenfolge_fest() -> None:
    namen = [v for v, _, _ in belege.ocr_varianten()]
    assert namen[:3] == ["grau-psm6", "grau-psm11", "grau-psm4"]
    assert namen[-1] == "schwelle-psm4"
    assert len(namen) == 15


# --- Abgrenzung: wann der Zweitversuch NICHT läuft -------------------------------------------

def _ocr_verboten(img: Image.Image, psm: str) -> str:
    raise AssertionError("Zweitversuch darf hier nicht laufen")


def test_beleg_mit_betrag_bitidentisch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Erkannter Betrag im ersten Durchgang: Ergebnis wie bisher, Cache-Verzeichnis unverändert."""
    periode, cache, _sha = _periode(tmp_path, erster_text="Gesamt 1.234,56 €\nDatum 14.08.2026")
    vorher = {f.name: f.read_bytes() for f in cache.iterdir()}
    monkeypatch.setattr(belege, "_ocr_bild", _ocr_verboten)
    monkeypatch.setattr(belege, "_bilder", lambda p: pytest.fail("Bilder dürfen nicht geladen werden"))
    b = _scan_einzeln(periode)
    erwartet = belege.analyse("Gesamt 1.234,56 €\nDatum 14.08.2026")
    assert b.alle == erwartet["alle"] == [Decimal("1234.56")]
    assert b.brutto == erwartet["brutto"]
    assert b.daten == erwartet["daten"]
    assert b.text == "Gesamt 1.234,56 €\nDatum 14.08.2026"
    assert b.ocr_variante is None
    assert {f.name: f.read_bytes() for f in cache.iterdir()} == vorher


def test_textbeleg_ohne_betrag_kein_zweitversuch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    periode = tmp_path / "p"
    periode.mkdir()
    (periode / "storno.txt").write_text("Cancellation confirmed", encoding="utf-8")
    monkeypatch.setattr(belege, "_ocr_bild", _ocr_verboten)
    b = _scan_einzeln(periode)
    assert b.alle == [] and b.ocr_variante is None


def test_ohne_treffer_bleibt_beleg_unveraendert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    periode, _, _ = _periode(tmp_path)
    fake = _fake_ocr(lambda img, psm: False)
    monkeypatch.setattr(belege, "_ocr_bild", fake)
    b = _scan_einzeln(periode)
    assert b.alle == [] and b.text == "unlesbar" and b.ocr_variante is None
    assert len(fake.aufrufe) == 15


def test_erste_passende_variante_gewinnt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    periode, _, _ = _periode(tmp_path)
    fake = _fake_ocr(lambda img, psm: True)
    monkeypatch.setattr(belege, "_ocr_bild", fake)
    b = _scan_einzeln(periode)
    assert b.ocr_variante == "grau-psm6"
    assert len(fake.aufrufe) == 1


def test_cache_je_variante_und_alter_cache_gueltig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    periode, cache, sha = _periode(tmp_path)
    erst = (cache / f"{sha}.txt").read_bytes()
    monkeypatch.setattr(belege, "_ocr_bild", _fake_ocr(lambda img, psm: psm == "11"))
    _scan_einzeln(periode)
    assert (cache / f"{sha}.txt").read_bytes() == erst
    assert sorted(f.name for f in cache.iterdir()) == sorted(
        [f"{sha}.txt", f"{sha}.grau-psm6.txt", f"{sha}.grau-psm11.txt"])
    # Zweiter Lauf: nur aus dem Cache, keine OCR
    monkeypatch.setattr(belege, "_ocr_bild", _ocr_verboten)
    monkeypatch.setattr(belege, "_bilder", lambda p: pytest.fail("Bilder dürfen nicht geladen werden"))
    b = _scan_einzeln(periode)
    assert b.ocr_variante == "grau-psm11" and b.alle == [Decimal("12.34")]


# --- echter Tesseract (übersprungen, wenn nicht installiert) ---------------------------------

@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract nicht installiert")
def test_echter_tesseract_liest_synthetischen_betrag(tmp_path: Path) -> None:
    img = Image.new("RGB", (900, 160), "white")
    font = ImageFont.load_default(size=56)
    ImageDraw.Draw(img).text((30, 40), "Summe 12,34 EUR", fill="black", font=font)
    text = belege._ocr_bild(belege.vv_grau(img), "6")
    assert Decimal("12.34") in belege.analyse(text)["alle"]
