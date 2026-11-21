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


def ergebnisaussage(a: Auswertung, results: list[SkillResult]) -> list[tuple[str, str, str]]:
    """Kernaussagen (Prüffrage, Ergebnis, Status) – analog zum Legacy-Bericht.

    Leitet den Status aus den Skill-Findings ab statt aus CheckResult-Metadaten.
    """
    by: dict[str, SkillResult] = {r.skill_id: r for r in results}

    def _sev_of(*skill_ids: str) -> str:
        sevs = {f.severity for sid in skill_ids for f in (by[sid].findings if sid in by else [])}
        if "fehler" in sevs:
            return "fehler"
        if "pruefen" in sevs:
            return "pruefen"
        return "ok"

    out: list[tuple[str, str, str]] = []

    # 1. Rechenwege korrekt?
    rech = ["bwa-rechenwege", "wertenachweis-abgleich", "summen-salden", "ergebnis-herleitung"]
    bad_rech = [f for sid in rech for f in (by[sid].findings if sid in by else []) if f.severity == "fehler"]
    mon_eur = _eur((a.bwa.get("Vorläufiges Ergebnis") or (None, None))[0])
    ytd_eur = _eur((a.bwa.get("Vorläufiges Ergebnis") or (None, None))[1])
    _rech_ok = (
        "Ja – BWA-Rechenwege, Wertenachweis, Summen/Salden und die unabhängige"
        " Herleitung aus den GuV-Konten stimmen überein."
    )
    if not bad_rech:
        out.append((
            f"Ist das Ergebnis rechnerisch richtig? (Monat {mon_eur}, Jahr {ytd_eur})",
            _rech_ok,
            "ok",
        ))
    else:
        out.append((
            f"Ist das Ergebnis rechnerisch richtig? (Monat {mon_eur}, Jahr {ytd_eur})",
            f"NEIN – {len(bad_rech)} Abweichung(en): " + "; ".join(f.title for f in bad_rech[:3]),
            "fehler",
        ))

    # 2. Jahresergebnis zum Vormonat?
    vm = by.get("vormonat-fortschreibung")
    if vm is not None:
        vm_fehler = [f for f in vm.findings if f.severity == "fehler"]
        if vm_fehler:
            j = next((f for f in vm_fehler if "Jahresergebnis" in f.title), vm_fehler[0])
            out.append((
                "Passt das Jahresergebnis zum Vormonat?",
                j.detail.split(" – es wurde")[0] + " → nachträgliche Buchungen in Vormonaten.",
                "fehler",
            ))
        elif any(f.title.startswith("Keine Vormonats") for f in vm.findings):
            out.append(("Passt das Jahresergebnis zum Vormonat?",
                        "Kein Vormonat vorhanden – Prüfung übersprungen.", "info"))
        else:
            out.append((
                "Passt das Jahresergebnis zum Vormonat?",
                "Ja – kum. Vormonat + Monat = kum. Berichtsmonat in allen BWA-Zeilen und Konten.",
                "ok",
            ))

    # 3. Umsatz belegt?
    u = by.get("umsatz-beweis")
    if u is not None:
        u_st = _sev_of("umsatz-beweis")
        if u_st == "ok":
            out.append(("Ist der Umsatz belegt?", "Umsatz vollständig durch Belege belegt.", "ok"))
        else:
            out.append((
                "Ist der Umsatz belegt?",
                f"Nein/teilweise – {len(u.findings)} Befund(e). Siehe Befunde zu umsatz-beweis.",
                u_st,
            ))

    # 4. Kosten belegt?
    d = by.get("kosten-deckung")
    if d is not None:
        d_st = _sev_of("kosten-deckung")
        out.append((
            "Sind die Kosten belegt?",
            "Eingangsbelege geprüft." if d_st == "ok"
            else f"Auffälligkeiten – {len(d.findings)} Befund(e).",
            d_st,
        ))

    # 5. UStVA korrekt?
    # Analog zur Legacy: "fehler" nur wenn tatsächlich Fehler; pruefen-Hinweise
    # (z.B. Konto 3820 ≠ Kz.83) gelten als "ok" für die Ergebnisaussage.
    us = by.get("ustva-abgleich")
    if us is not None:
        us_has_fehler = any(f.severity == "fehler" for f in us.findings)
        if not us_has_fehler:
            out.append((
                "Stimmt die Umsatzsteuer-Voranmeldung?",
                "Kz. 81/66/46/67/83 stimmen mit den Konten überein; Zahllast stimmt.",
                "ok",
            ))
        else:
            out.append((
                "Stimmt die Umsatzsteuer-Voranmeldung?",
                "Abweichungen – siehe Befunde zu ustva-abgleich.",
                "fehler",
            ))

    return out


def overall_severity(results: list[SkillResult]) -> str:
    sevs = {f.severity for r in results if not r.experimentell for f in r.findings}
    if "fehler" in sevs:
        return "fehler"
    if "pruefen" in sevs:
        return "pruefen"
    return "ok"


def to_markdown(a: Auswertung, results: list[SkillResult]) -> str:
    sev = overall_severity(results)
    nicht_exp = [r for r in results if not r.experimentell]
    n_skills = len(nicht_exp)
    n_findings = sum(len(r.findings) for r in nicht_exp)

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

    # Ergebnisaussage
    ea = ergebnisaussage(a, results)
    if ea:
        icon_ea = {"fehler": "🔴", "pruefen": "🟡", "info": "🔵", "ok": "🟢"}
        lines += ["## Ergebnisaussage", ""]
        for frage, antwort, status in ea:
            lines.append(f"**{icon_ea.get(status, '')} {frage}**  ")
            lines.append(f"{antwort}")
            lines.append("")

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

    # Befunde nach Schweregrad – nur nicht-experimentelle Skills
    for severity in ("fehler", "pruefen", "info"):
        relevant = [
            (r, f)
            for r in nicht_exp
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

    # Skills ohne Befund – nur nicht-experimentelle
    ok_skills = [r.skill_id for r in nicht_exp if not r.findings and not r.error]
    if ok_skills:
        lines += [
            "## 🟢 Ohne Befund",
            "",
            ", ".join(ok_skills),
            "",
        ]

    # Fehler beim Skill-Lauf – nur nicht-experimentelle
    errors = [(r.skill_id, r.error) for r in nicht_exp if r.error]
    if errors:
        lines += ["## ⚠️ Skill-Fehler", ""]
        for sid, err in errors:
            lines.append(f"- **{sid}**: {err.splitlines()[0] if err else '?'}")
        lines.append("")

    # KI-gestützt: experimentelle Skills (Findings NUR hier, nicht in obigen Abschnitten)
    exp_results = [r for r in results if r.experimentell]
    if exp_results:
        lines += ["## 🤖 KI-gestützt", ""]
        deaktiviert = [r for r in exp_results if r.deaktiviert]
        aktiv = [r for r in exp_results if not r.deaktiviert]
        if deaktiviert:
            sid_liste = ", ".join(r.skill_id for r in deaktiviert)
            lines.append(f"*Hinweis: experimentelle Skills deaktiviert ({sid_liste})*")
            lines.append("")
        for r in aktiv:
            lines.append(f"### {r.skill_id} *(experimentell)*")
            if r.error:
                lines.append(f"*Fehler: {r.error.splitlines()[0] if r.error else '?'}*")
            elif r.findings:
                for f in r.findings:
                    lines.append(f"**{f.title}**")
                    lines.append("")
                    for dl in f.detail.splitlines():
                        lines.append(dl)
                    lines.append("")
                # LLM-Zusammenfassung aus meta (falls Skill LLM-Aufruf dokumentiert hat)
                if "rueckfall_gruppen" in r.meta:
                    n_ges = r.meta.get("gruppen_gesamt", 0)
                    n_llm = r.meta.get("llm_gruppen", 0)
                    lines.append(
                        f"*Formulierung durch Modell: {n_llm} von {n_ges} Gruppen;"
                        " Rest als Standardtext*"
                    )
                    lines.append("")
            else:
                lines.append("*Keine Befunde.*")
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
        elif line.startswith("- **") and "**" in line[4:]:
            close = escaped.index("**", 4)
            body_lines.append(f"<li><strong>{escaped[4:close]}</strong>"
                               f"{escaped[close + 2:]}</li>")
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
