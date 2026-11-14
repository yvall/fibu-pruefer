"""Orchestrierung: BWA-PDF + Belegordner -> Prüfbericht."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import belege as belege_mod
from . import llm
from .checks import CheckResult, check_vormonat, run_bwa_checks
from .parser import Auswertung, load_auswertung
from .report import overall, to_html, to_markdown


@dataclass
class RunResult:
    auswertung: Auswertung
    results: list[CheckResult]
    md_path: Path
    html_path: Path
    status: str


def _bwa_dir(period_dir: Path, bwa_dirname: str) -> Path | None:
    return next((p for p in period_dir.iterdir() if p.is_dir() and p.name.lower() == bwa_dirname.lower()), None)


def list_bwa_pdfs(period_dir: Path, bwa_dirname: str = "BWA") -> list[tuple[tuple[int, int], Path]]:
    """Alle BWA-PDFs im BWA-Ordner mit (Jahr, Monat) aus dem Seitentitel – aufsteigend sortiert."""
    from .mail_fetch import _period_of
    d = _bwa_dir(period_dir, bwa_dirname)
    out = []
    for p in sorted(d.glob("*.[pP][dD][fF]")) if d else []:
        per = _period_of(p)
        if per:
            out.append((per, p))
    return sorted(out)


def find_bwa_pdf(period_dir: Path, bwa_dirname: str = "BWA") -> Path | None:
    """Das PDF des NEUESTEN Abrechnungsmonats (liegt zusätzlich der Vormonat im Ordner, wird er nur zum Vergleich genutzt)."""
    pdfs = list_bwa_pdfs(period_dir, bwa_dirname)
    if pdfs:
        return pdfs[-1][1]
    d = _bwa_dir(period_dir, bwa_dirname)
    fallback = sorted(d.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True) if d else []
    return fallback[0] if fallback else None


def run(period_dir: str | Path, bwa_dirname: str = "BWA", use_llm: bool = False) -> RunResult:
    period_dir = Path(period_dir)
    pdf = find_bwa_pdf(period_dir, bwa_dirname)
    if pdf is None:
        raise FileNotFoundError(f"Kein BWA-PDF in {period_dir / bwa_dirname}")
    a = load_auswertung(pdf)
    results = run_bwa_checks(a)
    prev = None
    for per, p in list_bwa_pdfs(period_dir, bwa_dirname):
        if p != pdf and per < (a.year, a.month):
            prev = load_auswertung(p)       # letzter Vormonat im Ordner
    results.append(check_vormonat(a, prev))
    belege = belege_mod.scan(period_dir, bwa_dirname)
    vm = next((x for x in results if x.key == "vormonat"), None)
    results.append(belege_mod.check_belege(a, belege))
    results.append(belege_mod.check_umsatz(a, belege))
    results.append(belege_mod.check_deckung(a, belege))
    kl = belege_mod.check_klaerung(a, belege, belege_mod.load_klaerung(period_dir), vm)
    if kl.findings or kl.tests:
        results.append(kl)
    summary = None
    if use_llm:
        txt = "\n".join(f"[{f.severity}] {f.title}: {f.detail}" for r in results for f in r.findings)
        summary = llm.summarize(txt)
    out = period_dir / "Pruefbericht"
    out.mkdir(exist_ok=True)
    stem = f"Pruefbericht_{a.year}-{a.month:02d}"
    md, ht = out / f"{stem}.md", out / f"{stem}.html"
    md.write_text(to_markdown(a, results, summary), encoding="utf-8")
    ht.write_text(to_html(a, results, summary), encoding="utf-8")
    return RunResult(a, results, md, ht, overall(results)[0])
