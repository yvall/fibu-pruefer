"""Skill summen-salden: interne Konsistenz der Summen & Salden prüfen."""
from __future__ import annotations

from decimal import Decimal

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Calc, Ref

ZERO = Decimal(0)


def _eur(val: Decimal) -> str:
    s = f"{val:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def run(ctx: Context) -> list[Finding]:
    a = ctx.auswertung
    tol = Decimal(str(ctx.config.get("toleranz", "0.02")))
    deb_sammel = str(ctx.config.get("debitoren_sammelkonto", "1200"))
    kred_sammel = str(ctx.config.get("kreditoren_sammelkonto", "3300"))

    findings: list[Finding] = []
    sach = {n: k for n, k in a.sus.items() if len(n) <= 4}

    # 1. Saldo = EB + Soll − Haben (je Konto)
    for n, k in a.sus.items():
        calc = k.eb + k.ytd_soll - k.ytd_haben
        diff = k.saldo - calc
        if abs(diff) > tol:
            findings.append(
                Finding(
                    rule="summen-salden",
                    severity="fehler",
                    title=f"Konto {n} {k.name}: Saldo passt nicht zu EB + Bewegungen",
                    detail=(
                        f"EB {_eur(k.eb)} + Soll {_eur(k.ytd_soll)} − Haben {_eur(k.ytd_haben)}"
                        f" = {_eur(calc)}, ausgewiesen {_eur(k.saldo)}."
                    ),
                    calc=Calc(erwartet=calc, ist=k.saldo, differenz=diff, formel="EB + Soll − Haben"),
                    refs=[Ref(art="konto", id=n, label=k.name)],
                )
            )

    # 2–3. Doppelte Buchhaltung Monat und kumuliert
    ps = sum((k.per_soll for k in sach.values()), ZERO)
    ph = sum((k.per_haben for k in sach.values()), ZERO)
    ys = sum((k.ytd_soll for k in sach.values()), ZERO)
    yh = sum((k.ytd_haben for k in sach.values()), ZERO)

    if abs(ps - ph) > tol:
        findings.append(
            Finding(
                rule="summen-salden",
                severity="fehler",
                title="Soll ≠ Haben im Monat",
                detail=f"Soll {_eur(ps)}, Haben {_eur(ph)}.",
                calc=Calc(erwartet=ph, ist=ps, differenz=ps - ph, formel="Σ per_soll = Σ per_haben"),
            )
        )
    if abs(ys - yh) > tol:
        findings.append(
            Finding(
                rule="summen-salden",
                severity="fehler",
                title="Soll ≠ Haben kumuliert",
                detail=f"Soll {_eur(ys)}, Haben {_eur(yh)}.",
                calc=Calc(erwartet=yh, ist=ys, differenz=ys - yh, formel="Σ ytd_soll = Σ ytd_haben"),
            )
        )

    # 4. Eröffnungsbilanz ausgeglichen
    eb_sum = sum((k.eb for k in sach.values()), ZERO)
    if abs(eb_sum) > tol:
        findings.append(
            Finding(
                rule="summen-salden",
                severity="fehler",
                title="Eröffnungsbilanz nicht ausgeglichen",
                detail="Summe der EB-Werte ist ungleich 0.",
                calc=Calc(erwartet=ZERO, ist=eb_sum, differenz=eb_sum, formel="Σ EB = 0"),
            )
        )

    # 5. Saldensumme = 0
    saldo_sum = sum((k.saldo for k in sach.values()), ZERO)
    if abs(saldo_sum) > tol:
        findings.append(
            Finding(
                rule="summen-salden",
                severity="fehler",
                title="Saldensumme ≠ 0",
                detail="Summe aller Salden (Soll − Haben) ist ungleich 0.",
                calc=Calc(erwartet=ZERO, ist=saldo_sum, differenz=saldo_sum, formel="Σ Saldo = 0"),
            )
        )

    # 6. Summenzeile plausibel
    if a.sus_total.get("per_soll") is not None:
        ps_total = a.sus_total["per_soll"]
        if abs(ps - ps_total) > tol:
            findings.append(
                Finding(
                    rule="summen-salden",
                    severity="pruefen",
                    title="Summenzeile (Monat Soll) ≠ Summe der Konten",
                    detail=f"Konten {_eur(ps)}, Summenzeile {_eur(ps_total)}.",
                    calc=Calc(
                        erwartet=ps_total, ist=ps, differenz=ps - ps_total,
                        formel="Σ per_soll = Summenzeile",
                    ),
                )
            )
        ytd_total = a.sus_total.get("ytd_soll")
        if ytd_total is not None and abs(ys - ytd_total) > tol:
            findings.append(
                Finding(
                    rule="summen-salden",
                    severity="pruefen",
                    title="Summenzeile (kum. Soll) ≠ Summe der Konten",
                    detail=f"Konten {_eur(ys)}, Summenzeile {_eur(ytd_total)}.",
                    calc=Calc(
                        erwartet=ytd_total, ist=ys, differenz=ys - ytd_total,
                        formel="Σ ytd_soll = Summenzeile",
                    ),
                )
            )

    # 7. Personenkonten ↔ Sammelkonten
    for first, sammel, label in (("1", deb_sammel, "Debitoren"), ("7", kred_sammel, "Kreditoren")):
        person = [k for n, k in a.sus.items() if len(n) == 5 and n.startswith(first)]
        if person and sammel in a.sus:
            s = sum((k.saldo for k in person), ZERO)
            diff = s - a.sus[sammel].saldo
            if abs(diff) > tol:
                findings.append(
                    Finding(
                        rule="summen-salden",
                        severity="fehler",
                        title=f"{label}: Personenkonten ≠ Sammelkonto {sammel}",
                        detail=f"Summe Personenkonten {_eur(s)}, Konto {sammel} {_eur(a.sus[sammel].saldo)}.",
                        calc=Calc(
                            erwartet=a.sus[sammel].saldo, ist=s, differenz=diff,
                            formel=f"Σ Personenkonten = Konto {sammel}",
                        ),
                        refs=[Ref(art="konto", id=sammel, label=label)],
                    )
                )

    return findings
