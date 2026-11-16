"""Skill opos-pruefung: Offene Posten Debitoren/Kreditoren prüfen."""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Ref

ZERO = Decimal(0)


def _eur(val: Decimal) -> str:
    s = f"{val:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def _pdate(s: str) -> date | None:
    for fmt in ("%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def run(ctx: Context) -> list[Finding]:
    a = ctx.auswertung
    tol = Decimal(str(ctx.config.get("toleranz", "0.02")))
    deb_sammel = str(ctx.config.get("debitoren_sammelkonto", "1200"))
    kred_sammel = str(ctx.config.get("kreditoren_sammelkonto", "3300"))

    findings: list[Finding] = []
    ref = _pdate(a.created) or date.today()
    end = (
        date(a.year, a.month, calendar.monthrange(a.year, a.month)[1])
        if a.year
        else ref
    )

    # 1. OPOS-Saldo je Konto ↔ Summen & Salden
    by: dict[str, list] = defaultdict(list)
    for it in a.opos:
        by[it.konto].append(it)
    for nr, items in by.items():
        s = sum((i.soll - i.haben for i in items), ZERO)
        k = a.sus.get(nr)
        if k and abs(s - k.saldo) > tol:
            findings.append(Finding(
                rule="opos-pruefung",
                severity="fehler",
                title=f"OPOS Konto {nr} ({items[0].konto_name}) ≠ Summen/Salden",
                detail=f"Offene Posten {_eur(s)}, Saldo {_eur(k.saldo)}.",
                refs=[Ref(art="konto", id=nr)],
            ))

    # 2. OPOS gesamt ↔ Sammelkonto
    for first, sammel, label in (("1", deb_sammel, "Debitoren"), ("7", kred_sammel, "Kreditoren")):
        s = sum((i.soll - i.haben for i in a.opos if i.konto.startswith(first)), ZERO)
        if sammel in a.sus and any(i.konto.startswith(first) for i in a.opos) and abs(s - a.sus[sammel].saldo) > tol:
            findings.append(Finding(
                rule="opos-pruefung",
                severity="fehler",
                title=f"OPOS {label} gesamt ≠ Sachkonto {sammel}",
                detail=f"OPOS {_eur(s)}, Sachkonto {_eur(a.sus[sammel].saldo)}.",
                refs=[Ref(art="konto", id=sammel)],
            ))

    # 3. Doppelte Rechnungsnummern
    seen: dict[tuple[str, str], int] = defaultdict(int)
    for it in a.opos:
        if it.belegnr:
            seen[(it.konto, it.belegnr)] += 1
    for (kto, nr), n in seen.items():
        if n != 1:
            findings.append(Finding(
                rule="opos-pruefung",
                severity="fehler",
                title=f"Rechnungsnummer {nr} doppelt auf Konto {kto}",
                detail=f"{n} offene Posten mit identischer Nummer.",
                refs=[Ref(art="konto", id=kto)],
            ))

    # 4. Rechnungen nach Periodenende + überfällige Forderungen
    overdue: list[tuple] = []
    for it in a.opos:
        if it.konto.startswith("1") and it.soll > 0:
            d = _pdate(it.datum)
            if d and d > end:
                findings.append(Finding(
                    rule="opos-pruefung",
                    severity="info",
                    title=(
                        f"Rechnung {it.belegnr} ({it.konto_name}) datiert nach Periodenende,"
                        f" aber im {a.month:02d}/{a.year} gebucht"
                    ),
                    detail=(
                        f"Rechnungsdatum {it.datum}, Betrag {_eur(it.soll)}. Zulässig bei Leistung"
                        f" im Berichtsmonat (Soll-Versteuerung) – Leistungsmonat anhand der"
                        f" Gutschrift/Rechnung prüfen."
                    ),
                    refs=[Ref(art="konto", id=it.konto)],
                ))
            f = _pdate(it.faellig)
            if f and f < ref:
                overdue.append((it, (ref - f).days))

    if overdue:
        total = sum((i.soll for i, _ in overdue), ZERO)
        lines = "; ".join(
            f"{i.konto_name} {i.belegnr} {_eur(i.soll)} ({d} Tage)"
            for i, d in sorted(overdue, key=lambda x: -x[1])
        )
        findings.append(Finding(
            rule="opos-pruefung",
            severity="pruefen",
            title=f"{len(overdue)} überfällige Forderungen, zusammen {_eur(total)}",
            detail=(
                f"Stand {ref:%d.%m.%Y}: {lines}. Zahlungseingänge auf dem Bankkonto prüfen"
                f" – evtl. bereits bezahlt, aber nicht ausgeziffert; sonst Mahnwesen."
            ),
            refs=[Ref(art="konto", id="OPOS")],
        ))

    return findings
