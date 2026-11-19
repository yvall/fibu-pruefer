#!/usr/bin/env python3
"""Eval-Lauf für skills/beleg-extraktion: Trefferquote je Feld.

Liest eine mit `fibu eval vorlage` erzeugte und manuell ausgefüllte JSON-Datei
und vergleicht die LLM-Extraktion mit dem Gold-Standard.
Zeigt zusätzlich die Baseline des deterministischen Legacy-Parsers.

Voraussetzungen:
  EVAL_REAL_DIR  Verzeichnis mit der ausgefüllten Vorlagendatei (vorlage_*.json)
  FIBU_LLM_MODELL oder config/lokal.yaml → llm.modell konfiguriert
  Ollama muss laufen

Aufruf:
  python evals/run_eval.py [--ordner <monat>] [--eval-dir <pfad>]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

# Projekt-Root zum sys.path hinzufügen (Aufruf direkt aus Repo-Root)
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO))  # für legacy-Imports


def _lade_vorlage(eval_dir: Path, monat: str) -> list[dict]:
    dateien = sorted(eval_dir.glob("vorlage_*.json"))
    if monat:
        dateien = [d for d in dateien if monat in d.name]
    if not dateien:
        raise FileNotFoundError(f"Keine Vorlagendatei in {eval_dir} (vorlage_*.json)")
    pfad = dateien[-1]
    print(f"Vorlage: {pfad}")
    return json.loads(pfad.read_text(encoding="utf-8"))


def _lade_skill() -> object:
    skill_path = _REPO / "skills" / "beleg-extraktion" / "check.py"
    spec = importlib.util.spec_from_file_location("_beleg_extraktion", skill_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Kann Skill nicht laden: {skill_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _vergleiche(gold: str, extrahiert: str) -> bool:
    """Normalisierter Feldvergleich (Whitespace, Groß-/Kleinschreibung)."""
    return gold.strip().lower() == extrahiert.strip().lower()


def _detail_zu_feldern(detail: str) -> dict[str, str]:
    """Extrahiert Felder aus Finding.detail-String.

    'Brutto:' → 'betrag'; 'Betrag-Regel:' → 'betrag_regel' (für Diagnose).
    """
    felder: dict[str, str] = {}
    for teil in detail.split(", "):
        if teil.startswith("Brutto: "):
            felder["betrag"] = teil[8:]
        elif teil.startswith("Betrag-Regel: "):
            felder["betrag_regel"] = teil[14:]
        elif teil.startswith("Datum: "):
            felder["datum"] = teil[7:]
        elif teil.startswith("Nr.: "):
            felder["nummer"] = teil[5:]
    return felder


def _format_betrag_de_simple(val: object) -> str:
    """Minimal-Formatter für Legacy-Decimal → '1.234,56'."""
    from decimal import Decimal
    d = Decimal(str(val)).quantize(Decimal("0.01"))
    s = str(d)
    int_p, dec_p = s.split(".") if "." in s else (s, "00")
    groups: list[str] = []
    while len(int_p) > 3:
        groups.insert(0, int_p[-3:])
        int_p = int_p[:-3]
    groups.insert(0, int_p)
    return ".".join(groups) + "," + dec_p


def _baseline_aus_text(text: str) -> dict[str, str]:
    """Führt den deterministischen Legacy-Parser auf dem Belegtext aus."""
    try:
        from legacy.fibu_pruefer.belege import analyse
        res = analyse(text)
        betrag = _format_betrag_de_simple(max(res["brutto"])) if res["brutto"] else ""
        datum = res["daten"][0] if res["daten"] else ""
        nummer = min(res["nummern"]) if res["nummern"] else ""
        return {"betrag": betrag, "datum": datum, "nummer": nummer}
    except Exception as exc:  # noqa: BLE001
        return {"betrag": "", "datum": "", "nummer": "", "_fehler": str(exc)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Eval-Lauf für beleg-extraktion")
    ap.add_argument(
        "--ordner", metavar="MONAT", default="",
        help="Monatsfilter für Vorlage (z. B. '08 Aug')",
    )
    ap.add_argument(
        "--eval-dir", metavar="PFAD", default="",
        help="Eval-Verzeichnis (überschreibt EVAL_REAL_DIR)",
    )
    args = ap.parse_args()

    eval_dir_str = args.eval_dir or os.environ.get("EVAL_REAL_DIR", "")
    if not eval_dir_str:
        print("FEHLER: EVAL_REAL_DIR nicht gesetzt (oder --eval-dir angeben)", file=sys.stderr)
        return 2
    eval_dir = Path(eval_dir_str)

    from fibu.config import LokaleConfig
    cfg = LokaleConfig.laden()
    if not cfg.llm.modell:
        print("FEHLER: Kein LLM-Modell konfiguriert (llm.modell oder FIBU_LLM_MODELL)", file=sys.stderr)
        return 2
    from fibu.llm.ollama import OllamaClient
    llm = OllamaClient.aus_config(cfg.llm)

    vorlage = _lade_vorlage(eval_dir, args.ordner)
    n_gesamt = len(vorlage)

    n_ungeprueft = sum(1 for e in vorlage if not e.get("geprueft", False))
    n_bewertet = n_gesamt - n_ungeprueft

    print(f"Modell       : {llm.modell}")
    print(
        f"Einträge     : {n_gesamt} gesamt"
        + (f", {n_ungeprueft} nicht geprüft (übersprungen)" if n_ungeprueft else "")
        + f", {n_bewertet} bewertet"
    )
    print()

    mod = _lade_skill()
    extrahiere = mod._extrahiere  # type: ignore[attr-defined]

    treffer:   dict[str, int] = {"betrag": 0, "datum": 0, "nummer": 0}
    gesamt:    dict[str, int] = {"betrag": 0, "datum": 0, "nummer": 0}
    leer:      dict[str, int] = {}
    base_treffer: dict[str, int] = {"betrag": 0, "datum": 0, "nummer": 0}
    base_leer:    dict[str, int] = {}
    laufzeiten: list[float] = []

    for eintrag in vorlage:
        rel = eintrag.get("beleg", "?")

        if not eintrag.get("geprueft", False):
            continue

        text = eintrag.get("text", eintrag.get("text_snippet", ""))
        if not text.strip():
            continue

        gold_felder = {f: eintrag.get(f, "") for f in ("betrag", "datum", "nummer")}

        # Baseline (deterministischer Legacy-Parser)
        baseline = _baseline_aus_text(text)

        t0 = time.perf_counter()
        findings = extrahiere(rel, text, llm)
        laufzeit = time.perf_counter() - t0
        laufzeiten.append(laufzeit)

        detail_info = next((f.detail for f in findings if f.severity == "info"), "")
        extrahiert = _detail_zu_feldern(detail_info)

        print(f"  [{laufzeit:.1f}s] {rel}")
        for feld in ("betrag", "datum", "nummer"):
            gold = gold_felder[feld]
            if not gold.strip():
                continue
            gesamt[feld] += 1
            got = extrahiert.get(feld, "")
            got_base = baseline.get(feld, "")

            # LLM+det. Ergebnis
            if not got:
                leer[feld] = leer.get(feld, 0) + 1
                llm_status = "leer"
            elif _vergleiche(gold, got):
                treffer[feld] += 1
                llm_status = f"✓ {gold!r}"
            else:
                llm_status = f"✗ erwartet={gold!r} erhalten={got!r}"
                if feld == "betrag":
                    regel = extrahiert.get("betrag_regel", "")
                    if regel:
                        llm_status += f" (Regel: {regel})"

            # Baseline
            if not got_base:
                base_leer[feld] = base_leer.get(feld, 0) + 1
                base_status = "leer"
            elif _vergleiche(gold, got_base):
                base_treffer[feld] += 1
                base_status = "✓"
            else:
                base_status = f"✗ {got_base!r}"

            print(f"    {feld:<8}: LLM={llm_status}  |  Basis={base_status}")

    # Zusammenfassung
    print()
    print(f"Modell       : {llm.modell}")
    if laufzeiten:
        avg = sum(laufzeiten) / len(laufzeiten)
        total = sum(laufzeiten)
        print(f"Laufzeit     : {len(laufzeiten)} Belege, ∅ {avg:.1f} s/Beleg, gesamt {total:.1f} s")
    if n_ungeprueft:
        print(f"Übersprungen : {n_ungeprueft} Einträge (geprueft=false)")

    print()
    _drucke_tabelle(gesamt, treffer, leer, base_treffer, base_leer)
    return 0


def _drucke_tabelle(
    gesamt: dict[str, int],
    treffer: dict[str, int],
    leer: dict[str, int],
    base_treffer: dict[str, int],
    base_leer: dict[str, int],
) -> None:
    """Gibt Baseline und LLM+det. Ergebnis in gemeinsamer Tabelle aus."""
    hdr = f"{'Feld':<10} {'Basis ✓':>8} {'Basis ✗':>8} {'Basis -':>8} {'Basis %':>8}  {'LLM ✓':>7} {'LLM ✗':>7} {'LLM -':>7} {'LLM %':>7}"
    print(hdr)
    print("-" * len(hdr))

    for feld in ("betrag", "datum", "nummer"):
        g = gesamt[feld]
        if g == 0:
            continue

        bt = base_treffer[feld]
        bl = base_leer.get(feld, 0)
        bf = g - bt - bl
        bq = f"{bt / g * 100:.1f}%" if g else "–"

        lt = treffer[feld]
        ll = leer.get(feld, 0)
        lf = g - lt - ll
        lq = f"{lt / g * 100:.1f}%" if g else "–"

        print(
            f"{feld:<10} {bt:>8} {bf:>8} {bl:>8} {bq:>8}  "
            f"{lt:>7} {lf:>7} {ll:>7} {lq:>7}"
        )

    print("-" * len(hdr))
    g_all = sum(gesamt.values())
    if g_all == 0:
        return

    bt_all = sum(base_treffer.values())
    bl_all = sum(base_leer.values())
    bf_all = g_all - bt_all - bl_all
    bq_all = f"{bt_all / g_all * 100:.1f}%"

    lt_all = sum(treffer.values())
    ll_all = sum(leer.values())
    lf_all = g_all - lt_all - ll_all
    lq_all = f"{lt_all / g_all * 100:.1f}%"

    print(
        f"{'gesamt':<10} {bt_all:>8} {bf_all:>8} {bl_all:>8} {bq_all:>8}  "
        f"{lt_all:>7} {lf_all:>7} {ll_all:>7} {lq_all:>7}"
    )
    print("* Quote = Richtig / Gesamt; Basis = deterministischer Legacy-Parser; LLM = det. Betrag + LLM Datum/Nr.")


if __name__ == "__main__":
    sys.exit(main())
