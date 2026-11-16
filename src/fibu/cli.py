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
    cfg = LokaleConfig.laden()
    print(f"Konfiguration: {cfg.config_quelle}")

    if a.ordner:
        period_dir = Path(str(a.ordner)).expanduser().resolve()
        if not period_dir.is_dir():
            raise FibuFehler(f"Ordner nicht gefunden: {period_dir}")
    else:
        root = _wurzel_aus_config(cfg)
        period_dir = _monat_aufloesen(root, str(a.monat))

    if a.legacy:
        return _cmd_pruefen_legacy(period_dir, a)

    return _cmd_pruefen_skills(period_dir, mit_mail=bool(a.mail))


def _cmd_pruefen_legacy(period_dir: Path, a: argparse.Namespace) -> int:
    """Prüfung über den Legacy-Pfad (python -m legacy.fibu_pruefer pruefen)."""
    from legacy.fibu_pruefer import pipeline

    try:
        res = pipeline.run(period_dir, use_llm=bool(a.llm))
    except FileNotFoundError:
        raise FibuFehler(f"Kein BWA-PDF in {period_dir / 'BWA'}")
    print(f"{res.status.upper()}  ->  {res.md_path}\n               {res.html_path}")
    return {"ok": 0, "pruefen": 1, "fehler": 2}.get(str(res.status), 2)


def _cmd_pruefen_skills(period_dir: Path, mit_mail: bool = False) -> int:
    """Prüfung über den Graph (Skills-Runtime)."""
    from fibu.graph.runner import run_pruefung

    try:
        result = run_pruefung(period_dir, skills_dir=Path("skills"), mit_mail=mit_mail)
    except FileNotFoundError as exc:
        raise FibuFehler(str(exc))

    if "__interrupt__" in result:
        lauf_id = result["lauf_id"]
        print("Lauf pausiert – Freigabe erforderlich.")
        print(f"Lauf-ID : {lauf_id}")
        print(f"Bericht : {result.get('bericht_md_pfad', '–')}")
        print("Freigabe: fibu freigeben --ordner <pfad> --freigabe ja")
        return 1

    sev = result["gesamtstatus"]
    md_path = result["bericht_md_pfad"]
    html_path = result["bericht_html_pfad"]
    print(f"{sev.upper()}  ->  {md_path}\n           {html_path}")
    return {"ok": 0, "pruefen": 1, "fehler": 2}.get(sev, 2)


def _cmd_freigeben(a: argparse.Namespace) -> int:
    from fibu.contracts import Entscheidung
    from fibu.graph.runner import freigeben_lauf
    from fibu.store import LaufStore

    cfg = LokaleConfig.laden()
    print(f"Konfiguration: {cfg.config_quelle}")

    if a.ordner:
        period_dir = Path(str(a.ordner)).expanduser().resolve()
    else:
        root = _wurzel_aus_config(cfg)
        period_dir = _monat_aufloesen(root, str(a.monat))

    store = LaufStore(cfg.store.sqlite_pfad)
    lauf = store.neuester_offener_lauf(str(period_dir))
    if lauf is None:
        raise FibuFehler(f"Kein offener Lauf für {period_dir}", exit_code=1)

    freigabe = "freigegeben" if a.freigabe == "ja" else "gesperrt"
    entscheidung = Entscheidung(freigabe=freigabe, kommentar=a.kommentar or "")  # type: ignore[arg-type]

    result = freigeben_lauf(lauf.lauf_id, entscheidung, store, trocken=bool(a.trocken))
    print(f"Lauf {lauf.lauf_id[:8]}… {freigabe}.")
    if result.get("bericht_md_pfad"):
        print(f"Bericht: {result['bericht_md_pfad']}")
    if result.get("versand_ok"):
        trocken_hinweis = " (Trockenlauf)" if a.trocken else ""
        print(f"Versand: ok{trocken_hinweis}")
    return 0


def _cmd_llm_pruefen(_a: argparse.Namespace) -> int:
    """Zeigt die LLM-Konfiguration und prüft Ollama-Erreichbarkeit und Modell-Status."""
    from fibu.llm.ollama import OllamaClient

    cfg = LokaleConfig.laden()
    print(f"Konfiguration: {cfg.config_quelle}")
    print()
    llm = cfg.llm

    print("Konfiguration")
    print(f"  Anbieter         : {llm.anbieter}")
    print(f"  URL              : {llm.url}")
    print(f"  Modell           : {llm.modell or '(nicht konfiguriert)'}")
    print(f"  Temperatur       : {llm.temperatur}")
    print(f"  Timeout          : {llm.timeout_sekunden} s")
    if llm.modell_zuordnung:
        print("  Modell-Zuordnung :")
        for skill_id, m in llm.modell_zuordnung.items():
            print(f"    {skill_id}: {m}")
    else:
        print("  Modell-Zuordnung : (keine)")
    print()

    if not llm.modell:
        print("FEHLER: Kein Modell konfiguriert.")
        print("  Setze 'llm.modell' in config/lokal.yaml oder FIBU_LLM_MODELL=<modell>")
        return 2

    client = OllamaClient.aus_config(llm)
    ok, meldung = client.ist_verfuegbar()

    erreichbar = ok or ("nicht installiert" in meldung)
    print("Ollama-Status")
    print(f"  Erreichbar       : {'ja' if erreichbar else 'NEIN'}")
    if not erreichbar:
        print(f"  Fehler           : {meldung}")
        return 2

    modell_ok = ok
    print(f"  Modell verfügbar : {'ja' if modell_ok else 'NEIN'}")
    if not modell_ok:
        print(f"  Hinweis          : {meldung}")
        return 2

    # Versionsnummer aus der OK-Meldung extrahieren
    version_hinweis = meldung  # z. B. "Ollama 0.5.1"
    print(f"  Version          : {version_hinweis}")
    print()

    # Structured Output testen
    print("Structured Output (format)")
    strukturiert = client.pruefe_structured_output()
    print(f"  Unterstützt      : {'ja' if strukturiert else 'nein (Fallback json.loads aktiv)'}")
    print()

    # Einfacher Test-Aufruf
    print("Test-Aufruf")
    antwort = client.generiere("Nenne die Zahl sieben auf Deutsch in einem Wort. Nur das Wort, nichts sonst.")
    if antwort is None:
        print("  Ergebnis         : FEHLER – kein Response")
        return 2
    print(f"  Antwort          : {antwort[:80]!r}")
    print("  Ergebnis         : ok")
    return 0


def _cmd_monate(_a: argparse.Namespace) -> int:
    from legacy.fibu_pruefer.pipeline import find_bwa_pdf

    config = LokaleConfig.laden()
    print(f"Konfiguration: {config.config_quelle}")
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
    p1.add_argument("--mail", action="store_true", help="Freigabe-Interrupt aktivieren (pausiert bis 'fibu freigeben')")

    sub.add_parser("monate", help="Periodenordner der Wurzel auflisten")

    p_llm = sub.add_parser("llm", help="LLM-Konfiguration und Ollama-Status")
    sub_llm = p_llm.add_subparsers(dest="llm_cmd", required=True)
    sub_llm.add_parser("pruefen", help="Konfiguration anzeigen, Ollama-Status und Modell prüfen")

    p_fg = sub.add_parser("freigeben", help="pausierten Prüflauf freigeben oder sperren")
    gruppe_fg = p_fg.add_mutually_exclusive_group(required=True)
    gruppe_fg.add_argument("--ordner", metavar="PFAD", help="Pfad zum Periodenordner")
    gruppe_fg.add_argument("--monat", metavar="NAME", help="Monatsordner (z. B. '08')")
    p_fg.add_argument("--freigabe", choices=["ja", "nein"], default="ja",
                      help="Freigabe erteilen (ja) oder sperren (nein)")
    p_fg.add_argument("--kommentar", metavar="TEXT", default="", help="Optionaler Kommentar")
    p_fg.add_argument("--trocken", action="store_true",
                      help="Trockenlauf: Versand wird protokolliert, aber keine Mail gesendet")

    a = ap.parse_args()
    try:
        if a.cmd == "pruefen":
            return _cmd_pruefen(a)
        if a.cmd == "freigeben":
            return _cmd_freigeben(a)
        if a.cmd == "llm":
            return _cmd_llm_pruefen(a)
        return _cmd_monate(a)
    except FibuFehler as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return e.exit_code


if __name__ == "__main__":
    sys.exit(main())
