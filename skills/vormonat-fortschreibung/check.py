"""Skill vormonat-fortschreibung: Vormonats-Fortschreibung und Rückwirkungsprüfung."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Ref

ZERO = Decimal(0)
_ENTW_TOL = Decimal("0.05")

# Exportiert durch run() für die Runtime (Phase 2: ctx.changed_accounts befüllen).
_meta: dict[str, Any] = {}


def _eur(val: Decimal) -> str:
    s = f"{val:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def _ust_watch(config: dict[str, Any]) -> set[str]:
    watch: set[str] = set()
    raw = config.get("ustva_konto_vorsteuer", ["1406", "1401"])
    watch.update(str(k) for k in raw) if isinstance(raw, list) else watch.update(["1406", "1401"])
    watch.add(str(config.get("ustva_konto_ust_19", "3806")))
    watch.add(str(config.get("ustva_konto_ust_13b", "3837")))
    watch.add(str(config.get("ustva_konto_vorsteuer_13b", "1407")))
    return watch


def run(ctx: Context) -> list[Finding]:
    global _meta
    a = ctx.auswertung
    p = ctx.prev
    tol = Decimal(str(ctx.config.get("toleranz", "0.02")))

    # --- Guard: kein Vormonat ---
    if p is None:
        _meta = {"changed": []}
        return [Finding(
            rule="vormonat-fortschreibung",
            severity="info",
            title="Keine Vormonats-BWA im BWA-Ordner",
            detail="Fortschreibung Vormonat → Berichtsmonat und Rückwirkungsprüfung wurden übersprungen.",
        )]

    # --- Guard: Vormonat nicht unmittelbar vorhergehend ---
    expected_prev = (a.year, a.month - 1) if a.month > 1 else (a.year - 1, 12)
    if (p.year, p.month) != expected_prev:
        _meta = {"changed": []}
        return [Finding(
            rule="vormonat-fortschreibung",
            severity="info",
            title="Vormonats-BWA nicht unmittelbar vorhergehend",
            detail=f"Vorhanden: {p.month:02d}/{p.year}, Berichtsmonat {a.month:02d}/{a.year}.",
        )]

    same_year = p.year == a.year
    findings: list[Finding] = []

    # --- 1. BWA-Fortschreibung (nur gleiches Jahr) ---
    if same_year:
        for lab, (per, ytd) in a.bwa.items():
            if lab not in p.bwa:
                continue
            exp = p.bwa[lab][1] + per
            if abs(exp - ytd) > tol:
                tag = "Jahresergebnis" if lab == "Vorläufiges Ergebnis" else lab
                findings.append(Finding(
                    rule="vormonat-fortschreibung",
                    severity="fehler",
                    title=f"{tag}: kum. Vormonat + Monat ≠ kum. Berichtsmonat",
                    detail=(
                        f"kum. {p.month:02d}: {_eur(p.bwa[lab][1])}"
                        f" + Monat {_eur(per)} = {_eur(exp)},"
                        f" ausgewiesen {_eur(ytd)}"
                        f" (Differenz {_eur(ytd - exp)}) –"
                        f" es wurde nachträglich in Vormonaten gebucht."
                    ),
                    refs=[Ref(art="seite", id="BWA")],
                ))

    # --- 2. Konten-Fortschreibung ---
    changed: list[tuple[str, str, Decimal, Decimal]] = []

    for n, k in a.sus.items():
        q = p.sus.get(n)
        if q is None:
            if same_year and (k.ytd_soll - k.per_soll > tol or k.ytd_haben - k.per_haben > tol):
                changed.append((n, k.name, k.ytd_soll - k.per_soll, k.ytd_haben - k.per_haben))
            continue
        if not same_year:
            continue
        dS = (k.ytd_soll - k.per_soll) - q.ytd_soll
        dH = (k.ytd_haben - k.per_haben) - q.ytd_haben
        if abs(dS) > tol or abs(dH) > tol:
            changed.append((n, k.name, dS, dH))

    for n, q in p.sus.items():
        if n not in a.sus and same_year and (abs(q.ytd_soll) > tol or abs(q.ytd_haben) > tol):
            changed.append((n, q.name + " (im Berichtsmonat nicht mehr bebucht)", -q.ytd_soll, -q.ytd_haben))

    _meta = {"changed": changed}

    if changed:
        txt = "; ".join(
            f"{n} {nm}: Soll {_eur(dS)} / Haben {_eur(dH)}"
            for n, nm, dS, dH in changed[:25]
        )
        ust = [c for c in changed if c[0] in _ust_watch(ctx.config)]
        if ust:
            txt += (
                " – ACHTUNG Umsatzsteuer: "
                + ", ".join(f"{c[0]} {_eur(c[2] - c[3])}" for c in ust)
                + " wurde rückwirkend verändert; diese Beträge sind in den bereits"
                " gemeldeten UStVA der Vormonate nicht enthalten und sind in der "
                "Aug-UStVA (Kz. 66 = nur Aug-Bewegung) nicht nachgeholt"
                " → ggf. berichtigte UStVA bzw. Nachmeldung beim Steuerberater erfragen."
            )
        findings.append(Finding(
            rule="vormonat-fortschreibung",
            severity="pruefen",
            title=f"{len(changed)} Konten mit nachträglich geänderten Vormonats-Buchungen",
            detail=(
                "Differenz zwischen kum. Werten des Berichtsmonats (abzüglich Monat)"
                " und den kum. Werten der Vormonats-BWA –"
                " also Buchungen mit Datum ≤ Vormonat, die nach Erstellung der"
                " Vormonats-BWA hinzukamen/geändert wurden: " + txt
            ),
            refs=[Ref(art="seite", id="Summen & Salden")],
        ))

    # --- 3. Entwicklungsübersicht ---
    diffs: list[tuple[str, str, Decimal, Decimal]] = []
    for lab, vals in a.entwicklung.items():
        pv = p.entwicklung.get(lab)
        if not pv:
            continue
        for i, m in enumerate(a.entw_months[:-1]):
            if m in p.entw_months:
                j = p.entw_months.index(m)
                if abs(vals[i] - pv[j]) > _ENTW_TOL:
                    diffs.append((lab, m, pv[j], vals[i]))

    if diffs:
        ocr = any(
            p.page_types.get(n) == "entwicklung"
            for n in (p.ocr_pages + a.ocr_pages)
        )
        diff_txt = "; ".join(
            f"{lab} {m}: {_eur(o)} → {_eur(nw)}"
            for lab, m, o, nw in diffs[:20]
        )
        note = " (Entwicklungsübersicht per OCR gelesen – ggf. Lesefehler)" if ocr else ""
        findings.append(Finding(
            rule="vormonat-fortschreibung",
            severity="pruefen" if not ocr else "info",
            title=f"{len(diffs)} Monatswerte früherer Monate haben sich seit der Vormonats-BWA geändert",
            detail=diff_txt + note,
            refs=[Ref(art="seite", id="Entwicklungsübersicht")],
        ))

    return findings
