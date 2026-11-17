#!/usr/bin/env python3
"""Eval-Lauf für skills/beleg-extraktion: Trefferquote je Feld.

Liest eine mit `fibu eval vorlage` erzeugte und manuell ausgefüllte JSON-Datei
und vergleicht die LLM-Extraktion mit dem Gold-Standard.

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
    """Extrahiert Felder aus Finding.detail-String."""
    felder: dict[str, str] = {}
    for teil in detail.split(", "):
        if teil.startswith("Betrag: "):
            felder["betrag"] = teil[8:]
        elif teil.startswith("Datum: "):
            felder["datum"] = teil[7:]
        elif teil.startswith("Nr.: "):
            felder["nummer"] = teil[5:]
    return felder


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

    # Einträge ohne ausgefüllte Gold-Felder werden übersprungen
    n_leer = sum(
        1 for e in vorlage
        if not any(e.get(f, "").strip() for f in ("betrag", "datum", "nummer"))
    )
    n_bewertet = n_gesamt - n_leer

    print(f"Modell       : {llm.modell}")
    print(
        f"Einträge     : {n_gesamt} gesamt"
        + (f", {n_leer} ohne Gold-Felder (übersprungen)" if n_leer else "")
        + f", {n_bewertet} bewertet"
    )
    print()

    mod = _lade_skill()
    extrahiere = mod._extrahiere  # type: ignore[attr-defined]

    treffer: dict[str, int] = {"betrag": 0, "datum": 0, "nummer": 0}
    gesamt: dict[str, int] = {"betrag": 0, "datum": 0, "nummer": 0}
    laufzeiten: list[float] = []

    for eintrag in vorlage:
        rel = eintrag.get("beleg", "?")
        text = eintrag.get("text", eintrag.get("text_snippet", ""))

        # Überspringe ohne Text oder ohne Gold-Felder
        if not text.strip():
            continue
        gold_felder = {f: eintrag.get(f, "") for f in ("betrag", "datum", "nummer")}
        if not any(v.strip() for v in gold_felder.values()):
            continue

        t0 = time.perf_counter()
        findings = extrahiere(rel, text, llm)
        laufzeit = time.perf_counter() - t0
        laufzeiten.append(laufzeit)

        extrahiert = _detail_zu_feldern(
            next((f.detail for f in findings if f.severity == "info"), "")
        )

        for feld in ("betrag", "datum", "nummer"):
            gold = gold_felder[feld]
            if not gold.strip():
                continue
            gesamt[feld] += 1
            ok = _vergleiche(gold, extrahiert.get(feld, ""))
            if ok:
                treffer[feld] += 1
                print(f"  ✓ {rel}: {feld}={gold!r}")
            else:
                got = extrahiert.get(feld, "(leer)")
                print(f"  ✗ {rel}: {feld}  erwartet={gold!r}  erhalten={got!r}")

    # Zusammenfassung
    print()
    print(f"Modell       : {llm.modell}")
    if laufzeiten:
        avg = sum(laufzeiten) / len(laufzeiten)
        total = sum(laufzeiten)
        print(f"Laufzeit     : {len(laufzeiten)} Belege, ∅ {avg:.1f} s/Beleg, gesamt {total:.1f} s")
    if n_leer:
        print(f"Übersprungen : {n_leer} Einträge (keine Gold-Felder ausgefüllt)")

    gesamt_t = sum(treffer.values())
    gesamt_g = sum(gesamt.values())

    print()
    print("Trefferquote je Feld:")
    print(f"{'Feld':<12} {'Treffer':>8} {'Gesamt':>8} {'Quote':>9}")
    print("-" * 44)
    for feld in ("betrag", "datum", "nummer"):
        g = gesamt[feld]
        t = treffer[feld]
        q = f"{t / g * 100:.1f} %" if g else "–"
        print(f"{feld:<12} {t:>8} {g:>8} {q:>9}")
    print("-" * 44)
    q_ges = f"{gesamt_t / gesamt_g * 100:.1f} %" if gesamt_g else "–"
    print(f"{'gesamt':<12} {gesamt_t:>8} {gesamt_g:>8} {q_ges:>9}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
