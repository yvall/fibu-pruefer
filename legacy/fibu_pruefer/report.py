"""Bericht (Markdown + HTML) aus den Prüfergebnissen."""
from __future__ import annotations

import html
from datetime import datetime

from decimal import Decimal

from .checks import CheckResult, eur, ORDER
from .parser import Auswertung

ICON = {"fehler": "🔴", "pruefen": "🟡", "info": "🔵", "ok": "🟢"}
LABEL = {"fehler": "Fehler", "pruefen": "Prüfen", "info": "Hinweis", "ok": "OK"}
MON = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]


def overall(results: list[CheckResult]) -> tuple[str, str]:
    sev = [f.severity for r in results for f in r.findings]
    if "fehler" in sev:
        return "fehler", "Fehler gefunden – Ergebnis nicht freigeben, Rückfrage an den Steuerberater."
    if "pruefen" in sev:
        return "pruefen", "Rechnerisch stimmig, aber mit Auffälligkeiten – Rückfragen empfohlen."
    return "ok", "Keine Beanstandungen."


def kennzahlen(a: Auswertung) -> list[tuple[str, str]]:
    g = lambda l, i: a.bwa.get(l, (None, None))[i]
    return [("Umsatzerlöse", f"{eur(g('Umsatzerlöse', 0))}  ·  kum. {eur(g('Umsatzerlöse', 1))}"),
            ("Gesamtkosten", f"{eur(g('Gesamtkosten', 0))}  ·  kum. {eur(g('Gesamtkosten', 1))}"),
            ("Betriebsergebnis", f"{eur(g('Betriebsergebnis', 0))}  ·  kum. {eur(g('Betriebsergebnis', 1))}"),
            ("Vorläufiges Ergebnis", f"{eur(g('Vorläufiges Ergebnis', 0))}  ·  kum. {eur(g('Vorläufiges Ergebnis', 1))}"),
            ("USt-Zahllast (Kz. 83)", eur((a.ustva.get("83") or {}).get("tax")))]


def ergebnisaussage(a: Auswertung, results: list[CheckResult]) -> list[tuple[str, str, str]]:
    """(Prüffrage, Ergebnis, Status) – die Kernaussage zu Monats- und Jahresergebnis."""
    R = {r.key: r for r in results}
    g = lambda l, i: a.bwa.get(l, (None, None))[i]
    out = []
    mon, ytd = eur(g("Vorläufiges Ergebnis", 0)), eur(g("Vorläufiges Ergebnis", 1))
    rech = [R[k] for k in ("bwa", "wertenachweis", "sus", "ergebnis") if k in R]
    bad = [f for r in rech for f in r.findings if f.severity == "fehler"]
    out.append((f"Ist das Ergebnis rechnerisch richtig? (Monat {mon}, Jahr {ytd})",
                "Ja – BWA-Rechenwege, Wertenachweis, Summen/Salden und die unabhängige Herleitung aus den GuV-Konten stimmen überein." if not bad
                else f"NEIN – {len(bad)} Abweichung(en): " + "; ".join(f.title for f in bad[:3]), "fehler" if bad else "ok"))
    v = R.get("vormonat")
    if v is not None:
        fe = [f for f in v.findings if f.severity == "fehler"]
        if fe:
            j = next((f for f in fe if f.title.startswith("Jahresergebnis")), fe[0])
            out.append(("Passt das Jahresergebnis zum Vormonat?", j.detail.split(" – es wurde")[0] + " → nachträgliche Buchungen in Vormonaten (siehe Befund „Konten mit nachträglich geänderten Vormonats-Buchungen“).", "fehler"))
        elif v.tests > 5:
            out.append(("Passt das Jahresergebnis zum Vormonat?", "Ja – kum. Vormonat + Monat = kum. Berichtsmonat in allen BWA-Zeilen und Konten.", "ok"))
    u = R.get("umsatz")
    if u is not None:
        st = u.status
        out.append(("Ist der Umsatz belegt?", u.meta.get("umsatz_ok") or "Nein/teilweise – siehe Befunde zu Umsatzerlösen.", "pruefen" if st == "ok" and not u.meta.get("umsatz_ok") else st if st != "info" else "ok"))
    d = R.get("deckung")
    if d is not None and d.meta:
        cov = (d.meta["belege"] / d.meta["booked"] * 100) if d.meta["booked"] else Decimal(0)
        out.append(("Sind die Kosten belegt?", f"Eingangsbelege decken {cov:.0f} % der gebuchten Belegkosten ({eur(d.meta['belege'])} von {eur(d.meta['booked'])}); Personal-, AfA- und Mietkosten sind nicht durch den Ordner belegbar.", d.status))
    us = R.get("ustva")
    if us is not None:
        out.append(("Stimmt die Umsatzsteuer-Voranmeldung?", "Kz. 81/66/46/67/83 stimmen mit den Konten überein; Zahllast stimmt mit Anschreiben und Protokoll." if not any(f.severity == "fehler" for f in us.findings) else "Abweichungen – siehe Befunde.", "ok" if not any(f.severity in ("fehler",) for f in us.findings) else "fehler"))
    return out


def _sorted_findings(results: list[CheckResult]):
    items = [(f, r.name) for r in results for f in r.findings]
    return sorted(items, key=lambda x: ORDER[x[0].severity])


def to_markdown(a: Auswertung, results: list[CheckResult], summary: str | None = None) -> str:
    st, text = overall(results)
    n_tests = sum(r.tests for r in results)
    L = [f"# Prüfbericht Buchhaltung {MON[a.month]} {a.year}", "",
         f"**Gesamtbewertung: {ICON[st]} {text}**", "",
         f"Quelle: `{a.source.name}` · Auswertung vom {a.created} · geprüft {datetime.now():%d.%m.%Y %H:%M} · {n_tests} automatische Einzelprüfungen", ""]
    if summary:
        L += ["## Zusammenfassung", summary, ""]
    L += ["## Kernaussage zu Monats- und Jahresergebnis", "", "| Frage | Ergebnis | |", "|---|---|---|"]
    L += [f"| {q} | {e} | {ICON[s]} |" for q, e, s in ergebnisaussage(a, results)]
    L += ["", "## Kennzahlen laut Steuerberater", "", "| Kennzahl | Monat / kumuliert |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in kennzahlen(a)]
    L += ["", "## Prüfblöcke", "", "| Block | Einzelprüfungen | Befunde | Status |", "|---|---:|---:|---|"]
    for r in results:
        L.append(f"| {r.name} | {r.tests} | {len(r.findings)} | {ICON[r.status]} {LABEL[r.status]} |")
    L.append("")
    for sev in ("fehler", "pruefen", "info"):
        items = [(f, n) for f, n in _sorted_findings(results) if f.severity == sev]
        if not items:
            continue
        L += [f"## {ICON[sev]} {LABEL[sev]} ({len(items)})", ""]
        for i, (f, n) in enumerate(items, 1):
            L.append(f"{i}. **{f.title}**" + (f" _({f.ref})_" if f.ref else ""))
            L.append(f"   {f.detail}")
        L.append("")
    if a.rueckfragen:
        L += ["## Rückfragen des Steuerberaters laut Anschreiben", ""]
        L += [f"- {q.datum + ' – ' if q.datum else ''}{eur(q.betrag) + ' – ' if q.betrag is not None else ''}{q.text}" for q in a.rueckfragen]
        L.append("")
    if a.warnings:
        L += ["## Hinweise zur Datenqualität", ""] + [f"- {w}" for w in a.warnings] + [""]
    L += ["---", "_Automatisch erstellt. Alle Zahlen sind deterministisch nachgerechnet; Befunde sind Prüfhinweise, keine Buchungsanweisungen._"]
    return "\n".join(L)


CSS = """body{font:15px/1.5 system-ui,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;color:#1b1f24}
h1{margin-bottom:.2rem}table{border-collapse:collapse;margin:.5rem 0 1.2rem;width:100%}th,td{border-bottom:1px solid #d8dde3;padding:.35rem .5rem;text-align:left}
td.n,th.n{text-align:right}.f{border-left:4px solid;padding:.4rem .8rem;margin:.5rem 0;background:#f6f8fa}.fehler{border-color:#d1242f}.pruefen{border-color:#bf8700}.info{border-color:#0969da}
.ref{color:#667;font-size:.85em}.banner{padding:.8rem 1rem;border-radius:6px;font-weight:600;margin:1rem 0}.b-ok{background:#dafbe1}.b-pruefen{background:#fff8c5}.b-fehler{background:#ffebe9}"""


def to_html(a: Auswertung, results: list[CheckResult], summary: str | None = None) -> str:
    st, text = overall(results)
    e = html.escape
    h = [f"<!doctype html><meta charset=utf-8><title>Prüfbericht {MON[a.month]} {a.year}</title><style>{CSS}</style>",
         f"<h1>Prüfbericht Buchhaltung {MON[a.month]} {a.year}</h1>",
         f"<div class='banner b-{st}'>{ICON[st]} {e(text)}</div>",
         f"<p class=ref>Quelle {e(a.source.name)} · Auswertung vom {e(a.created)} · geprüft {datetime.now():%d.%m.%Y %H:%M}</p>"]
    if summary:
        h.append(f"<h2>Zusammenfassung</h2><p>{e(summary)}</p>")
    h.append("<h2>Kernaussage zu Monats- und Jahresergebnis</h2><table><tr><th>Frage<th>Ergebnis<th></tr>" + "".join(
        f"<tr><td>{e(q)}<td>{e(x)}<td>{ICON[s]}</tr>" for q, x, s in ergebnisaussage(a, results)) + "</table>")
    h.append("<h2>Kennzahlen laut Steuerberater</h2><table>" + "".join(f"<tr><td>{e(k)}</td><td>{e(v)}</td></tr>" for k, v in kennzahlen(a)) + "</table>")
    h.append("<h2>Prüfblöcke</h2><table><tr><th>Block<th class=n>Einzelprüfungen<th class=n>Befunde<th>Status</tr>" +
             "".join(f"<tr><td>{e(r.name)}<td class=n>{r.tests}<td class=n>{len(r.findings)}<td>{ICON[r.status]} {LABEL[r.status]}</tr>" for r in results) + "</table>")
    for sev in ("fehler", "pruefen", "info"):
        items = [(f, n) for f, n in _sorted_findings(results) if f.severity == sev]
        if items:
            h.append(f"<h2>{ICON[sev]} {LABEL[sev]} ({len(items)})</h2>")
            for f, n in items:
                h.append(f"<div class='f {sev}'><b>{e(f.title)}</b> <span class=ref>{e(f.ref)}</span><br>{e(f.detail)}</div>")
    if a.rueckfragen:
        h.append("<h2>Rückfragen des Steuerberaters</h2><ul>" + "".join(
            f"<li>{e(q.datum)} {e(eur(q.betrag)) if q.betrag is not None else ''} {e(q.text)}</li>" for q in a.rueckfragen) + "</ul>")
    if a.warnings:
        h.append("<h2>Datenqualität</h2><ul>" + "".join(f"<li>{e(w)}</li>" for w in a.warnings) + "</ul>")
    return "\n".join(h)
