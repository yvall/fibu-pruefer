"""Skill ergebnis-herleitung: Ergebnis unabhängig aus GuV-Konten herleiten."""
from __future__ import annotations

from decimal import Decimal

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Calc, Ref

ZERO = Decimal(0)
_LAB = "Vorläufiges Ergebnis"


def _eur(val: Decimal) -> str:
    s = f"{val:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def run(ctx: Context) -> list[Finding]:
    a = ctx.auswertung
    tol = Decimal(str(ctx.config.get("toleranz", "0.02")))

    guv = {n: k for n, k in a.sus.items() if len(n) == 4 and n[0] in "45678"}

    if not guv or _LAB not in a.bwa:
        return [
            Finding(
                rule="ergebnis-herleitung",
                severity="pruefen",
                title="Ergebnisherleitung nicht möglich",
                detail="GuV-Konten oder BWA-Ergebniszeile fehlen.",
            )
        ]

    mon = sum((k.per_haben - k.per_soll for k in guv.values()), ZERO)
    ytd = sum((k.ytd_haben - k.ytd_soll for k in guv.values()), ZERO)
    bwa_mon, bwa_ytd = a.bwa[_LAB]

    findings: list[Finding] = []

    if abs(mon - bwa_mon) > tol:
        findings.append(
            Finding(
                rule="ergebnis-herleitung",
                severity="fehler",
                title=f"Monatsergebnis {a.month:02d}/{a.year} stimmt nicht",
                detail=(
                    f"Aus den GuV-Konten (Klassen 4–8) ergibt sich {_eur(mon)},"
                    f" die BWA weist {_eur(bwa_mon)} aus"
                    f" (Differenz {_eur(bwa_mon - mon)})."
                ),
                calc=Calc(
                    erwartet=bwa_mon, ist=mon, differenz=mon - bwa_mon,
                    formel="Σ(Haben − Soll) der GuV-Konten",
                ),
                refs=[Ref(art="seite", id="Summen & Salden ↔ BWA")],
            )
        )

    if abs(ytd - bwa_ytd) > tol:
        findings.append(
            Finding(
                rule="ergebnis-herleitung",
                severity="fehler",
                title=f"Jahresergebnis Jan–{a.month:02d}/{a.year} stimmt nicht",
                detail=(
                    f"Aus den GuV-Konten ergibt sich {_eur(ytd)},"
                    f" die BWA weist {_eur(bwa_ytd)} aus"
                    f" (Differenz {_eur(bwa_ytd - ytd)})."
                ),
                calc=Calc(
                    erwartet=bwa_ytd, ist=ytd, differenz=ytd - bwa_ytd,
                    formel="Σ(kum. Haben − kum. Soll) der GuV-Konten",
                ),
                refs=[Ref(art="seite", id="Summen & Salden ↔ BWA")],
            )
        )

    return findings
