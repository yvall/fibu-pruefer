from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fibu.config import LokaleConfig


class FibuFehler(Exception):
    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _perioden_ordner(root: Path) -> list[Path]:
    """Alle Periodenordner in root – ohne Ordner mit _/. am Anfang oder 'Pruef' im Namen."""
    return sorted(
        p for p in root.iterdir()
        if p.is_dir()
        and not p.name.startswith((".", "_"))
        and "Pruef" not in p.name
    )


def _monat_aufloesen(root: Path, name: str) -> Path:
    """Liefert den eindeutigen Periodenordner, dessen Name mit name beginnt."""
    ordner = _perioden_ordner(root)
    treffer = [o for o in ordner if o.name.startswith(name)]
    if not treffer:
        raise FibuFehler(f"Monat '{name}' nicht gefunden in {root}.")
    if len(treffer) > 1:
        namen = ", ".join(o.name for o in treffer)
        raise FibuFehler(f"Monat '{name}' ist mehrdeutig: {namen}")
    return treffer[0]


def _wurzel_aus_config(config: LokaleConfig) -> Path:
    if config.daten.wurzel is None:
        raise FibuFehler(
            "Datenwurzel nicht konfiguriert. "
            "Bitte FIBU_DATEN_WURZEL setzen oder config/lokal.yaml anlegen."
        )
    root = config.daten.wurzel
    if not root.is_dir():
        raise FibuFehler(f"Datenwurzel nicht gefunden: {root}")
    return root


def _cmd_pruefen(a: argparse.Namespace) -> int:
    if a.ordner:
        period_dir = Path(str(a.ordner)).expanduser().resolve()
        if not period_dir.is_dir():
            raise FibuFehler(f"Ordner nicht gefunden: {period_dir}")
    else:
        cfg = LokaleConfig.laden()
        root = _wurzel_aus_config(cfg)
        period_dir = _monat_aufloesen(root, str(a.monat))

    if a.legacy:
        return _cmd_pruefen_legacy(period_dir, a)

    return _cmd_pruefen_skills(period_dir)


def _cmd_pruefen_legacy(period_dir: Path, a: argparse.Namespace) -> int:
    """Prüfung über den Legacy-Pfad (python -m legacy.fibu_pruefer pruefen)."""
    from legacy.fibu_pruefer import pipeline

    try:
        res = pipeline.run(period_dir, use_llm=bool(a.llm))
    except FileNotFoundError:
        raise FibuFehler(f"Kein BWA-PDF in {period_dir / 'BWA'}")
    print(f"{res.status.upper()}  ->  {res.md_path}\n               {res.html_path}")
    return {"ok": 0, "pruefen": 1, "fehler": 2}.get(str(res.status), 2)


def _cmd_pruefen_skills(period_dir: Path) -> int:
    """Prüfung über den Graph (Skills-Runtime)."""
    from fibu.graph.runner import run_pruefung

    try:
        result = run_pruefung(period_dir, skills_dir=Path("skills"))
    except FileNotFoundError as exc:
        raise FibuFehler(str(exc))

    sev = result["gesamtstatus"]
    md_path = result["bericht_md_pfad"]
    html_path = result["bericht_html_pfad"]
    print(f"{sev.upper()}  ->  {md_path}\n           {html_path}")
    return {"ok": 0, "pruefen": 1, "fehler": 2}.get(sev, 2)


def _cmd_monate(_a: argparse.Namespace) -> int:
    from legacy.fibu_pruefer.pipeline import find_bwa_pdf

    config = LokaleConfig.laden()
    root = _wurzel_aus_config(config)
    ordner = _perioden_ordner(root)
    if not ordner:
        print(f"Keine Periodenordner in {root}")
        return 0
    for o in ordner:
        pdf = find_bwa_pdf(o, config.daten.bwa_ordner)
        marker = "✓" if pdf else "–"
        print(f"{o.name:<24}  BWA: {marker}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="fibu", description="Prüfung der Steuerberater-Buchhaltung")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("pruefen", help="einen Periodenordner prüfen")
    gruppe = p1.add_mutually_exclusive_group(required=True)
    gruppe.add_argument(
        "--monat", metavar="NAME", help="Monatsordner (z. B. '08 Aug' oder Kurzform '08')"
    )
    gruppe.add_argument("--ordner", metavar="PFAD", help="voller Pfad zum Periodenordner")
    p1.add_argument("--llm", action="store_true", help="Zusammenfassung per lokalem Ollama formulieren (nur mit --legacy)")
    p1.add_argument("--legacy", action="store_true", help="Legacy-Pipeline statt Skills-Runtime verwenden")

    sub.add_parser("monate", help="Periodenordner der Wurzel auflisten")

    a = ap.parse_args()
    try:
        if a.cmd == "pruefen":
            return _cmd_pruefen(a)
        return _cmd_monate(a)
    except FibuFehler as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return e.exit_code


if __name__ == "__main__":
    sys.exit(main())
