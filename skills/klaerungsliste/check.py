"""Skill klaerungsliste: Klärungsliste gg. Konto 1370 / Belege."""
from __future__ import annotations

from decimal import Decimal

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Ref
from legacy.fibu_pruefer.belege import find_combos  # type: ignore[import]

ZERO = Decimal(0)
_LQ = "„"  # deutschen Anführungszeichen: unten
_RQ = "“"  # deutschen Anführungszeichen: oben
_UGP = f"{_LQ}Ungeklärte Posten{_RQ}"  # „Ungeklärte Posten"


def _eur(val: Decimal) -> str:
    s = f"{val:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def run(ctx: Context) -> list[Finding]:
    a = ctx.auswertung
    rows = ctx.klaerung
    belege = ctx.belege
    changed = ctx.changed_accounts

    if not rows:
        return []

    findings: list[Finding] = []
    eps = Decimal("0.005")
    rowamts = [
        (x, x.betrag)
        for x in rows
        if x.betrag is not None and x.betrag > 0
        and not x.text.lower().startswith(("101_", "\t"))
    ]

    # 1. Offene 1370-Posten ↔ Klärungsliste
    jk = next((j for j in a.jahreskonten if j.nr == "1370"), None)
    if jk:
        for e in jk.entries:
            amt = abs(e.soll - e.haben)
            m = next((x for x, v in rowamts if abs(v - amt) <= eps), None)
            if m:
                findings.append(Finding(
                    rule="klaerungsliste",
                    severity="info",
                    title=f"Konto 1370 {e.datum} {_eur(amt)} {_LQ}{e.text[:35]}{_RQ}: in Klärungsliste geführt",
                    detail=f"Kommentar: {m.kommentar or '–'}",
                    refs=[Ref(art="konto", id="1370")],
                ))
            elif not e.text.startswith("Deutsche Bank"):
                findings.append(Finding(
                    rule="klaerungsliste",
                    severity="pruefen",
                    title=f"Konto 1370 {e.datum} {_eur(amt)} {_LQ}{e.text[:35]}{_RQ} fehlt in der Klärungsliste",
                    detail=f"Posten offen, aber nicht in {_UGP}.",
                    refs=[Ref(art="konto", id="1370")],
                ))

    # 2. Klärungsliste ↔ Belege / Konto
    open_amts = [abs(e.soll - e.haben) for e in (jk.entries if jk else [])]
    for x, v in rowamts:
        beleg = next((b for b in belege if any(abs(v - y) <= eps for y in b.brutto)), None)
        still = any(abs(v - o) <= eps for o in open_amts)
        if beleg:
            suffix = "" if still else " Auf Konto 1370 nicht mehr offen."
            findings.append(Finding(
                rule="klaerungsliste",
                severity="info",
                title=f"Klärung {_LQ}{x.text[:40]}{_RQ} {_eur(v)}: Beleg mit identischem Betrag gefunden",
                detail=(
                    f"{beleg.rel} – bitte inhaltlich bestätigen;"
                    f" dann kann der Steuerberater den Posten umbuchen.{suffix}"
                ),
            ))
        elif not still:
            findings.append(Finding(
                rule="klaerungsliste",
                severity="info",
                title=f"Klärung {_LQ}{x.text[:40]}{_RQ} {_eur(v)}: nicht mehr auf Konto 1370 offen",
                detail="Vermutlich bereits umgebucht (siehe Umbuchungen unten) – Liste bereinigen.",
            ))

    # 3. Umbuchungen aus dem Vormonatsvergleich erklären
    if changed:
        for n, nm, dS, dH in changed:
            delta = dS - dH
            if abs(delta) < Decimal(1):
                continue
            tgt = abs(delta)
            hits = find_combos(tgt, [(x, v) for x, v in rowamts], max_items=4, limit=2)
            if hits:
                findings.append(Finding(
                    rule="klaerungsliste",
                    severity="info",
                    title=f"Konto {n} {nm}: nachträgliche Änderung {_eur(delta)} erklärbar",
                    detail=(
                        "Entspricht Klärungsliste: "
                        + " + ".join(f"{c[0].text[:30]} {_eur(c[1])}" for c in hits[0])
                        + " (Umbuchung nach Klärung)."
                    ),
                    refs=[Ref(art="konto", id=n)],
                ))

    # 4. Negative Monatsbewegung auf 1370 ↔ Liste + Beleg
    k = a.sus.get("1370")
    if k and k.per_soll < 0:
        v = -k.per_soll
        xl = next((x for x, y in rowamts if abs(y - v) <= eps), None)
        b = next((bl for bl in belege if any(abs(v - y) <= eps for y in bl.brutto)), None)
        if xl or b:
            findings.append(Finding(
                rule="klaerungsliste",
                severity="info",
                title=f"Konto 1370: Monatsbewegung −{_eur(v)} nachvollziehbar",
                detail=(
                    f"Klärungsliste: {xl.text if xl else '–'}"
                    f" ({xl.kommentar if xl else ''});"
                    f" Beleg: {b.rel if b else '–'}."
                    f" Erledigter Klärungsposten wurde ausgebucht."
                ),
                refs=[Ref(art="konto", id="1370")],
            ))

    return findings
