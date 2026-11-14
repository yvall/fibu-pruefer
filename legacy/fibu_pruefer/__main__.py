import argparse
import sys
from pathlib import Path

from . import mail_fetch, pipeline, watcher


def main() -> int:
    ap = argparse.ArgumentParser(prog="fibu_pruefer", description="Prüfung der Steuerberater-Buchhaltung")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("pruefen", help="einen Periodenordner (z. B. '08 Aug') prüfen")
    p1.add_argument("ordner")
    p1.add_argument("--llm", action="store_true", help="Zusammenfassung per lokalem Ollama formulieren")
    p2 = sub.add_parser("watch", help="Wurzelordner überwachen (neue BWA -> automatische Prüfung)")
    p2.add_argument("wurzel")
    p2.add_argument("--intervall", type=int, default=60)
    p2.add_argument("--mail", action="store_true", help="IMAP-Eingang abfragen und Bericht per SMTP senden")
    p2.add_argument("--llm", action="store_true")
    a = ap.parse_args()
    if a.cmd == "pruefen":
        res = pipeline.run(a.ordner, use_llm=a.llm)
        print(f"{res.status.upper()}  ->  {res.md_path}\n               {res.html_path}")
        return {"ok": 0, "pruefen": 1, "fehler": 2}[res.status]
    root = Path(a.wurzel)
    watcher.watch(root, a.intervall, notify=mail_fetch.send_report if a.mail else None, use_llm=a.llm,
                  mail_fetch=(lambda r: mail_fetch.fetch_new(r)) if a.mail else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
