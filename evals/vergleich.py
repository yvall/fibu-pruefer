#!/usr/bin/env python3
"""Vergleich der letzten Eval-Läufe für skills/beleg-extraktion.

Liest alle bericht_*.json aus dem Eval-Ordner und gibt Modell, Quote und
Falsch-Anteil je Feld sowie Laufzeit nebeneinander aus.

Aufruf:
  python evals/vergleich.py [--eval-dir <pfad>] [--n <anzahl>]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))

FELDER = ("betrag", "datum", "nummer")


def _lade_berichte(eval_dir: Path) -> list[dict]:
    """Liest alle bericht_*.json und sortiert sie nach Datum absteigend."""
    dateien = sorted(eval_dir.glob("bericht_*.json"), reverse=True)
    berichte: list[dict] = []
    for d in dateien:
        try:
            b = json.loads(d.read_text(encoding="utf-8"))
            b.setdefault("_datei", d.name)
            berichte.append(b)
        except (json.JSONDecodeError, OSError):
            pass
    return berichte


def _pct(zaehler: int, nenner: int) -> str:
    if nenner == 0:
        return "   –  "
    return f"{zaehler / nenner * 100:5.1f}%"


def _format_tabelle(berichte: list[dict]) -> str:
    """Gibt Berichte als formatierte Tabelle zurück (eine Spalte pro Lauf)."""
    if not berichte:
        return "(keine Berichte gefunden)"

    # Spaltenbreite aus längstem Modellnamen ableiten (min 16)
    spalte_w = max(16, max(len(b.get("modell", "")) for b in berichte))
    n = len(berichte)
    label_w = 22  # Zeilenbeschriftung

    def _sp(s: str) -> str:
        return str(s).ljust(spalte_w)

    lines: list[str] = []
    lines.append(f"Eval-Vergleich  ({n} Lauf{'¨e' if n != 1 else ''})")
    lines.append("")

    # Header: Datum-Zeile + Modell-Zeile
    lines.append(" " * label_w + "  ".join(_sp(b.get("datum", "?")) for b in berichte))
    lines.append(" " * label_w + "  ".join(_sp(b.get("modell", "?")) for b in berichte))
    sep = "-" * (label_w + (spalte_w + 2) * n - 2)
    lines.append(sep)

    def _zeile(label: str, werte: list[str]) -> str:
        return label.ljust(label_w) + "  ".join(w.ljust(spalte_w) for w in werte)

    # Metadaten
    lines.append(_zeile(
        "N Belege",
        [str(b.get("n_belege", "?")) for b in berichte],
    ))
    lines.append(_zeile(
        "Laufzeit ∅",
        [f"{b.get('laufzeit_avg_s', 0):.1f} s" for b in berichte],
    ))
    lines.append(sep)

    # Felder
    for feld in FELDER:
        lines.append(_zeile(
            f"{feld}  ✓ Gesamt",
            [
                _pct(b["felder"][feld]["llm_treffer"], b["felder"][feld]["gesamt"])
                if feld in b.get("felder", {}) else "–"
                for b in berichte
            ],
        ))
        lines.append(_zeile(
            f"{feld}  ✗ Falsch",
            [
                _pct(b["felder"][feld]["llm_falsch"], b["felder"][feld]["gesamt"])
                if feld in b.get("felder", {}) else "–"
                for b in berichte
            ],
        ))
        lines.append(_zeile(
            f"{feld}  ✓ Einsatz",
            [
                _pct(
                    b["felder"][feld]["einsatz_llm_treffer"],
                    b["felder"][feld]["einsatz_gesamt"],
                )
                if feld in b.get("felder", {}) else "–"
                for b in berichte
            ],
        ))
        lines.append("")

    # Gesamt (über alle Felder)
    def _sum_feld(b: dict, key: str) -> int:
        return sum(b.get("felder", {}).get(f, {}).get(key, 0) for f in FELDER)

    lines.append(sep)
    lines.append(_zeile(
        "gesamt  ✓",
        [_pct(_sum_feld(b, "llm_treffer"), _sum_feld(b, "gesamt")) for b in berichte],
    ))
    lines.append(_zeile(
        "gesamt  ✗",
        [_pct(_sum_feld(b, "llm_falsch"), _sum_feld(b, "gesamt")) for b in berichte],
    ))
    lines.append(_zeile(
        "gesamt  ✓ Einsatz",
        [
            _pct(_sum_feld(b, "einsatz_llm_treffer"), _sum_feld(b, "einsatz_gesamt"))
            for b in berichte
        ],
    ))

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Vergleich der letzten Eval-Läufe")
    ap.add_argument("--eval-dir", metavar="PFAD", default="",
                    help="Eval-Verzeichnis (überschreibt EVAL_REAL_DIR)")
    ap.add_argument("--n", type=int, default=0, metavar="ANZAHL",
                    help="Nur die letzten N Läufe anzeigen (0 = alle)")
    args = ap.parse_args()

    eval_dir_str = args.eval_dir or os.environ.get("EVAL_REAL_DIR", "")
    if not eval_dir_str:
        print("FEHLER: EVAL_REAL_DIR nicht gesetzt (oder --eval-dir angeben)",
              file=sys.stderr)
        return 2
    eval_dir = Path(eval_dir_str)

    berichte = _lade_berichte(eval_dir)
    if args.n > 0:
        berichte = berichte[: args.n]

    print(_format_tabelle(berichte))
    return 0


if __name__ == "__main__":
    sys.exit(main())
