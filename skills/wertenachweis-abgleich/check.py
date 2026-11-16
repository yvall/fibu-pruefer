"""Skill wertenachweis-abgleich: Wertenachweis-Konten gegen BWA und Summen & Salden prüfen."""
from __future__ import annotations

import difflib
from decimal import Decimal

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Ref

ZERO = Decimal(0)


def _eur(val: Decimal) -> str:
    s = f"{val:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def _fuzzy(label: str, known: list[str]) -> str | None:
    if label in known:
        return label
    m = difflib.get_close_matches(label, known, n=1, cutoff=0.7)
    return m[0] if m else None


def run(ctx: Context) -> list[Finding]:
    a = ctx.auswertung
    tol = Decimal(str(ctx.config.get("toleranz", "0.02")))

    findings: list[Finding] = []

    for g in a.wgroups:
        sev = "pruefen" if g.ocr else "fehler"
        note = " (Seite per OCR gelesen – ggf. Lesefehler)" if g.ocr else ""
        sp = sum((k.per for k in g.kontos), ZERO)
        sy = sum((k.ytd for k in g.kontos), ZERO)
        ref_zeile = Ref(art="seite", id=f"Zeile {g.zeile}")

        if g.bwa_per is not None and abs(sp - g.bwa_per) > tol:
            findings.append(Finding(
                rule="wertenachweis-abgleich",
                severity=sev,
                title=f"Zeile {g.zeile} {g.name}: Konten ≠ BWA-Wert (Monat)",
                detail=f"Summe der Konten {_eur(sp)}, BWA-Zeile {_eur(g.bwa_per)}{note}.",
                refs=[ref_zeile],
            ))
        if g.bwa_ytd is not None and abs(sy - g.bwa_ytd) > tol:
            findings.append(Finding(
                rule="wertenachweis-abgleich",
                severity=sev,
                title=f"Zeile {g.zeile} {g.name}: Konten ≠ BWA-Wert (kumuliert)",
                detail=f"Summe der Konten {_eur(sy)}, BWA-Zeile {_eur(g.bwa_ytd)}{note}.",
                refs=[ref_zeile],
            ))

        lab = _fuzzy(g.name, list(a.bwa))
        if lab and g.bwa_per is not None and abs(a.bwa[lab][0] - g.bwa_per) > tol:
            findings.append(Finding(
                rule="wertenachweis-abgleich",
                severity=sev,
                title=f"Zeile {g.zeile} {g.name}: Wertenachweis ≠ BWA-Seite",
                detail=f"BWA-Seite {_eur(a.bwa[lab][0])}, Wertenachweis {_eur(g.bwa_per)}{note}.",
                refs=[ref_zeile],
            ))
        if lab and g.bwa_ytd is not None and abs(a.bwa[lab][1] - g.bwa_ytd) > tol:
            findings.append(Finding(
                rule="wertenachweis-abgleich",
                severity=sev,
                title=f"Zeile {g.zeile} {g.name}: Wertenachweis ≠ BWA-Seite (kum.)",
                detail=f"BWA-Seite {_eur(a.bwa[lab][1])}, Wertenachweis {_eur(g.bwa_ytd)}{note}.",
                refs=[ref_zeile],
            ))

        for k in g.kontos:
            sk = a.sus.get(k.nr)
            if not sk:
                continue
            sign = 1 if k.sh == "S" else -1
            exp_p = sign * sk.per_move
            exp_y = sign * sk.ytd_move
            ref_konto = Ref(art="konto", id=k.nr)
            if abs(k.per - exp_p) > tol:
                findings.append(Finding(
                    rule="wertenachweis-abgleich",
                    severity=sev,
                    title=f"Konto {k.nr} {k.name}: Wertenachweis ≠ Summen/Salden (Monat)",
                    detail=f"Wertenachweis {_eur(k.per)}, Summen/Salden {_eur(exp_p)}{note}.",
                    refs=[ref_konto],
                ))
            if abs(k.ytd - exp_y) > tol:
                findings.append(Finding(
                    rule="wertenachweis-abgleich",
                    severity=sev,
                    title=f"Konto {k.nr} {k.name}: Wertenachweis ≠ Summen/Salden (kum.)",
                    detail=f"Wertenachweis {_eur(k.ytd)}, Summen/Salden {_eur(exp_y)}{note}.",
                    refs=[ref_konto],
                ))

    return findings
