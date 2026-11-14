"""Ordner-Watcher: startet die Prüfung automatisch, sobald eine neue BWA (oder neue Belege) vorliegt."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .pipeline import find_bwa_pdf, run

STATE = ".fibu_pruefer_state.json"


def _fingerprint(period: Path, bwa: Path) -> str:
    h = hashlib.sha1(bwa.read_bytes())
    for p in sorted(period.rglob("*")):
        if p.is_file() and "Pruefbericht" not in p.parts and p != bwa and not p.name.startswith("."):
            h.update(f"{p.relative_to(period)}:{p.stat().st_size}".encode())
    return h.hexdigest()


def scan_once(root: Path, settle: int = 20, notify=None, use_llm: bool = False) -> list[Path]:
    state_file = root / STATE
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    done: list[Path] = []
    for period in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_", "Pruef"))):
        bwa = find_bwa_pdf(period)
        if not bwa:
            continue
        if time.time() - bwa.stat().st_mtime < settle:      # Datei wird evtl. noch geschrieben
            continue
        fp = _fingerprint(period, bwa)
        if state.get(str(period)) == fp:
            continue
        try:
            res = run(period, use_llm=use_llm)
        except Exception as e:  # noqa: BLE001
            print(f"[watcher] {period.name}: Fehler {e!r}")
            continue
        state[str(period)] = fp
        state_file.write_text(json.dumps(state, indent=1))
        done.append(res.md_path)
        print(f"[watcher] {period.name}: {res.status} -> {res.md_path}")
        if notify:
            notify(res)
    return done


def watch(root: str | Path, interval: int = 60, settle: int = 20, notify=None, use_llm: bool = False, mail_fetch=None) -> None:
    root = Path(root)
    print(f"[watcher] überwache {root} alle {interval}s")
    while True:
        if mail_fetch:
            try:
                mail_fetch(root)
            except Exception as e:  # noqa: BLE001
                print(f"[mail] Fehler {e!r}")
        scan_once(root, settle, notify, use_llm)
        time.sleep(interval)
