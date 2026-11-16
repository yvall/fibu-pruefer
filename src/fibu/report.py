"""Prüfbericht aus SkillResults (Markdown + HTML)."""
from __future__ import annotations

import html as _html
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fibu.contracts import Auswertung
from fibu.skills_runtime import SkillResult

_ICON: dict[str, str] = {"fehler": "🔴", "pruefen": "🟡", "info": "🔵"}
_LABEL: dict[str, str] = {"fehler": "Fehler", "pruefen": "Auffälligkeiten", "info": "Hinweise"}
_MON = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
        "August", "September", "Oktober", "November", "Dezember"]
_ORDER = {"fehler": 0, "pruefen": 1, "info": 2}


def _eur(v: Decimal | None) -> str:
    if v is None:
        return "–"
    s = f"{v:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def overall_severity(results: list[SkillResult]) -> str:
    sevs = {f.severity for r in results for f in r.findings}
    if "fehler" in sevs:
        return "fehler"
    if "pruefen" in sevs:
        return "pruefen"
    return "ok"


def to_markdown(a: Auswertung, results: list[SkillResult]) -> str:
    sev = overall_severity(results)
    n_skills = len(results)
    n_findings = sum(len(r.findings) for r in results)

    icon_map = {"fehler": "🔴", "pruefen": "🟡", "ok": "🟢"}
    text_map = {
        "fehler": "Fehler gefunden – Ergebnis nicht freigeben, Rückfrage an den Steuerberater.",
        "pruefen": "Rechnerisch stimmig, aber mit Auffälligkeiten – Rückfragen empfohlen.",
        "ok": "Keine Beanstandungen.",
    }

    lines: list[str] = [
        f"# Prüfbericht Buchhaltung {_MON[a.month]} {a.year}",
        "",
        f"**Gesamtbewertung: {icon_map[sev]} {text_map[sev]}**",
        "",
        (
            f"Quelle: `{Path(a.source).name}`"
            f"  ·  Auswertung vom {a.created}"
            f"  ·  geprüft {datetime.now():%d.%m.%Y %H:%M}"
            f"  ·  {n_skills} Skills, {n_findings} Befunde"
        ),
        "",
    ]

    # Kennzahlen aus BWA
    kz_lines: list[str] = []
    for label in ("Umsatzerlöse", "Gesamtkosten", "Betriebsergebnis", "Vorläufiges Ergebnis"):
        v = a.bwa.get(label)
        if v:
            kz_lines.append(f"| {label} | {_eur(v[0])} | {_eur(v[1])} |")
    if kz_lines:
        lines += [
            "## Kennzahlen",
            "",
            "| Zeile | Monat | Kumuliert |",
            "|---|---|---|",
            *kz_lines,
            "",
        ]

    # Befunde nach Schweregrad
    for severity in ("fehler", "pruefen", "info"):
        relevant = [
            (r, f)
            for r in results
            for f in r.findings
            if f.severity == severity
        ]
        if not relevant:
            continue
        lines += [f"## {_ICON[severity]} {_LABEL[severity]} ({len(relevant)})", ""]
        last_rule = ""
        for r, f in relevant:
            if r.skill_id != last_rule:
                lines.append(f"### {r.skill_id}")
                last_rule = r.skill_id
            lines.append(f"- **{f.title}**  ")
            lines.append(f"  {f.detail}")
        lines.append("")

    # Skills ohne Befund
    ok_skills = [r.skill_id for r in results if not r.findings and not r.error]
    if ok_skills:
        lines += [
            "## 🟢 Ohne Befund",
            "",
            ", ".join(ok_skills),
            "",
        ]

    # Fehler beim Skill-Lauf
    errors = [(r.skill_id, r.error) for r in results if r.error]
    if errors:
        lines += ["## ⚠️ Skill-Fehler", ""]
        for sid, err in errors:
            lines.append(f"- **{sid}**: {err.splitlines()[0] if err else '?'}")
        lines.append("")

    return "\n".join(lines)


def to_html(a: Auswertung, results: list[SkillResult]) -> str:
    md = to_markdown(a, results)
    # Einfache Markdown→HTML-Konvertierung (kein externer Renderer nötig)
    body_lines: list[str] = []
    in_table = False
    for line in md.splitlines():
        escaped = _html.escape(line)
        if line.startswith("# "):
            body_lines.append(f"<h1>{_html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body_lines.append(f"<h2>{_html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            body_lines.append(f"<h3>{_html.escape(line[4:])}</h3>")
        elif line.startswith("|") and "|---|" not in line:
            if not in_table:
                body_lines.append("<table>")
                in_table = True
            cells = [c.strip() for c in line.split("|")[1:-1]]
            body_lines.append("<tr>" + "".join(f"<td>{_html.escape(c)}</td>" for c in cells) + "</tr>")
        elif in_table and not line.startswith("|"):
            body_lines.append("</table>")
            in_table = False
            if line:
                body_lines.append(f"<p>{escaped}</p>")
        elif line.startswith("- **") and "**" in line[2:]:
            body_lines.append(f"<li><strong>{escaped[6:escaped.index('**', 6)]}</strong>"
                               f"{escaped[escaped.index('**', 6)+2:]}</li>")
        elif line.startswith("- "):
            body_lines.append(f"<li>{_html.escape(line[2:])}</li>")
        elif line.startswith("**") and line.endswith("**"):
            body_lines.append(f"<p><strong>{_html.escape(line[2:-2])}</strong></p>")
        elif line == "":
            if in_table:
                body_lines.append("</table>")
                in_table = False
        else:
            body_lines.append(f"<p>{escaped}</p>")
    if in_table:
        body_lines.append("</table>")

    body = "\n".join(body_lines)
    sev = overall_severity(results)
    color = {"fehler": "#c0392b", "pruefen": "#f39c12", "ok": "#27ae60"}.get(sev, "#333")
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<title>Prüfbericht {_MON[a.month]} {a.year}</title>
<style>
  body{{font-family:system-ui,sans-serif;max-width:900px;margin:2em auto;padding:0 1em;color:#333}}
  h1{{border-bottom:3px solid {color};padding-bottom:.3em}}
  h2{{margin-top:1.5em}} h3{{color:#555;font-size:1em}}
  table{{border-collapse:collapse;width:100%}} td{{border:1px solid #ddd;padding:.4em .6em}}
  li{{margin:.2em 0}} strong{{color:#222}}
</style></head>
<body>
{body}
</body></html>
"""
