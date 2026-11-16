"""Skill entwicklung-ausreisser: 13-Monats-Entwicklungsübersicht prüfen."""
from __future__ import annotations

import statistics
from decimal import Decimal

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Ref

ZERO = Decimal(0)

# OCR-Toleranz für BWA-Vergleich ist 0,05 €, nicht die allgemeine toleranz.
_BWA_TOL = Decimal("0.05")

_SKIP_OUTLIER = {
    "Gesamtleistung", "Rohertrag", "Betriebl. Rohertrag",
    "Gesamtkosten", "Ergebnis vor Steuern",
}
_OUTLIER_MIN_ABS = Decimal(250)
_OUTLIER_MIN_REL = Decimal("0.15")


def _eur(val: Decimal) -> str:
    s = f"{val:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def run(ctx: Context) -> list[Finding]:
    a = ctx.auswertung
    pk_schwelle = Decimal(str(ctx.config.get("personalkosten_ausreisser_schwelle", "10000")))

    if not a.entwicklung:
        return [Finding(
            rule="entwicklung-ausreisser",
            severity="pruefen",
            title="Entwicklungsübersicht nicht lesbar",
            detail="Keine 13-Monats-Zeilen erkannt.",
        )]

    ocr = 6 in a.ocr_pages or any(
        p in a.ocr_pages for p in range(1, 99) if a.page_types.get(p) == "entwicklung"
    )
    sev = "pruefen" if ocr else "fehler"
    note = " (OCR-Seite)" if ocr else ""
    _ref = Ref(art="seite", id="Entwicklungsübersicht")

    findings: list[Finding] = []
    outlier: list[tuple[str, Decimal, Decimal, Decimal, Decimal]] = []

    for lab, vals in a.entwicklung.items():
        bw = a.bwa.get(lab)
        if bw:
            if abs(vals[-1] - bw[0]) > _BWA_TOL:
                findings.append(Finding(
                    rule="entwicklung-ausreisser",
                    severity=sev,
                    title=f"{lab}: Monatswert Entwicklungsübersicht ≠ BWA",
                    detail=f"Entwicklung {_eur(vals[-1])}, BWA {_eur(bw[0])}{note}.",
                    refs=[_ref],
                ))
            ytd = sum(vals[-a.month:], ZERO)
            if abs(ytd - bw[1]) > _BWA_TOL:
                findings.append(Finding(
                    rule="entwicklung-ausreisser",
                    severity=sev,
                    title=f"{lab}: Summe Jan–{a.month:02d} ≠ kumulierter BWA-Wert",
                    detail=f"Σ Monate {_eur(ytd)}, BWA kumuliert {_eur(bw[1])}{note}.",
                    refs=[_ref],
                ))

        if lab in _SKIP_OUTLIER:
            continue
        prev = vals[:-1]
        if not any(prev):
            continue
        med = Decimal(str(statistics.median([float(x) for x in prev])))
        lo, hi = min(prev), max(prev)
        cur = vals[-1]
        if (
            (cur < lo or cur > hi)
            and abs(cur - med) >= _OUTLIER_MIN_ABS
            and abs(cur - med) >= abs(med) * _OUTLIER_MIN_REL
        ):
            outlier.append((lab, cur, med, lo, hi))

    for lab, cur, med, lo, hi in outlier:
        findings.append(Finding(
            rule="entwicklung-ausreisser",
            severity="info",
            title=f"{lab}: Monatswert außerhalb der 12-Monats-Spanne",
            detail=f"{_eur(cur)} (Median Vormonate {_eur(med)}, Spanne {_eur(lo)} … {_eur(hi)}).",
            refs=[_ref],
        ))

    pk = a.entwicklung.get("Personalkosten")
    if pk:
        med = Decimal(str(statistics.median([float(x) for x in pk])))
        for m, v in zip(a.entw_months, pk):
            if abs(v - med) > pk_schwelle:
                findings.append(Finding(
                    rule="entwicklung-ausreisser",
                    severity="info",
                    title=f"Personalkosten {m}: stark abweichend ({_eur(v)})",
                    detail=(
                        f"Median {_eur(med)}. Bei Abweichung > 10.000 € "
                        f"Rückstellungsbuchung/Tantieme/Einmalzahlung belegen lassen "
                        f"(Konten 3074/6026 in Summen & Salden)."
                    ),
                    refs=[_ref],
                ))

    return findings
