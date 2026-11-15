"""Skill bwa-rechenwege: Rechenwege der BWA prüfen (Monat und kumuliert)."""
from __future__ import annotations

from decimal import Decimal

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Calc, Ref

ZERO = Decimal(0)

_COST_LINES = [
    "Personalkosten",
    "Raumkosten",
    "Betriebl. Steuern",
    "Versich./Beiträge",
    "Besondere Kosten",
    "Fahrzeugko. (o. St)",
    "Werbe-/Reisekosten",
    "Kosten Warenabgabe",
    "Abschreibungen",
    "Reparatur/Instandh.",
    "Sonstige Kosten",
]


def _eur(val: Decimal) -> str:
    s = f"{val:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def run(ctx: Context) -> list[Finding]:
    a = ctx.auswertung
    tol = Decimal(str(ctx.config.get("toleranz", "0.02")))

    if not a.bwa:
        return [
            Finding(
                rule="bwa-rechenwege",
                severity="fehler",
                title="BWA nicht lesbar",
                detail="Die BWA-Seite konnte nicht ausgewertet werden.",
                refs=[Ref(art="seite", id="BWA")],
            )
        ]

    def v(label: str, idx: int) -> Decimal:
        x = a.bwa.get(label)
        return x[idx] if x is not None else ZERO

    findings: list[Finding] = []
    for idx, per in ((0, f"{a.month:02d}/{a.year}"), (1, f"Jan–{a.month:02d}/{a.year}")):
        rules: list[tuple[str, Decimal, str]] = [
            (
                "Gesamtleistung",
                v("Umsatzerlöse", idx) + v("Best.Verdg. FE/UE", idx) + v("Akt.Eigenleistungen", idx),
                "Umsatz + Bestandsveränd. + Eigenleistungen",
            ),
            (
                "Rohertrag",
                v("Gesamtleistung", idx) - v("Mat./Wareneinkauf", idx),
                "Gesamtleistung − Wareneinkauf",
            ),
            (
                "Betriebl. Rohertrag",
                v("Rohertrag", idx) + v("So. betr. Erlöse", idx),
                "Rohertrag + sonst. betr. Erlöse",
            ),
            (
                "Gesamtkosten",
                sum((v(c, idx) for c in _COST_LINES), ZERO),
                "Summe der Kostenarten",
            ),
            (
                "Betriebsergebnis",
                v("Betriebl. Rohertrag", idx) - v("Gesamtkosten", idx),
                "Betriebl. Rohertrag − Gesamtkosten",
            ),
            (
                "Neutraler Aufwand",
                v("Zinsaufwand", idx) + v("Sonst. neutr. Aufw", idx),
                "Zinsaufwand + sonst. neutr. Aufwand",
            ),
            (
                "Neutraler Ertrag",
                v("Zinserträge", idx) + v("Sonst. neutr. Ertr", idx) + v("Verr. kalk. Kosten", idx),
                "Zinserträge + sonst. neutr. Erträge + verr. kalk. Kosten",
            ),
            (
                "Ergebnis vor Steuern",
                v("Betriebsergebnis", idx)
                - v("Neutraler Aufwand", idx)
                + v("Neutraler Ertrag", idx)
                + v("Kontenkl. unbesetzt", idx),
                "Betriebsergebnis − neutr. Aufwand + neutr. Ertrag",
            ),
            (
                "Vorläufiges Ergebnis",
                v("Ergebnis vor Steuern", idx) - v("Steuern Eink.u.Ertr", idx),
                "Ergebnis vor Steuern − Ertragsteuern",
            ),
        ]
        for label, calc, formel in rules:
            if label not in a.bwa:
                continue
            shown = v(label, idx)
            diff = shown - calc
            if abs(diff) > tol:
                findings.append(
                    Finding(
                        rule="bwa-rechenwege",
                        severity="fehler",
                        title=f"BWA {per}: „{label}“ stimmt nicht",
                        detail=(
                            f"Ausgewiesen {_eur(shown)}, nachgerechnet {_eur(calc)}"
                            f" ({formel}); Differenz {_eur(diff)}."
                        ),
                        calc=Calc(erwartet=calc, ist=shown, differenz=diff, formel=formel),
                        refs=[Ref(art="seite", id="BWA")],
                    )
                )
    return findings
