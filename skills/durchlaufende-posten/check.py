"""Skill durchlaufende-posten: Jahreskonten (Durchlaufende Posten) prüfen."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Ref

ZERO = Decimal(0)
_LQUOTE = "„"  # deutschen Anführungszeichen: unten  „
_RQUOTE = "“"  # deutschen Anführungszeichen: oben   "
_DASH = "–"    # Gedankenstrich –


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
    max_tage = int(ctx.config.get("ueberfaellig_tage", 60))

    findings: list[Finding] = []
    ref = _pdate(a.created) or date.today()

    for jk in a.jahreskonten:
        ref_konto = Ref(art="konto", id=jk.nr, label=jk.name)
        calc = jk.eb + jk.jvz_soll - jk.jvz_haben

        if abs(jk.saldo - calc) > tol:
            findings.append(Finding(
                rule="durchlaufende-posten",
                severity="fehler",
                title=f"Konto {jk.nr} {jk.name}: Saldo rechnerisch falsch",
                detail=f"EB + Soll − Haben = {_eur(calc)}, ausgewiesen {_eur(jk.saldo)}.",
                refs=[ref_konto],
            ))

        es = sum((e.soll for e in jk.entries), ZERO)
        eh = sum((e.haben for e in jk.entries), ZERO)
        if abs(es - jk.jvz_soll) > tol or abs(eh - jk.jvz_haben) > tol:
            findings.append(Finding(
                rule="durchlaufende-posten",
                severity="fehler",
                title=f"Konto {jk.nr}: Einzelposten ≠ Summenzeile",
                detail=(
                    f"Einzelposten Soll {_eur(es)} / Haben {_eur(eh)},"
                    f" Summenzeile {_eur(jk.jvz_soll)} / {_eur(jk.jvz_haben)}."
                ),
                refs=[ref_konto],
            ))

        if abs(jk.saldo) > tol:
            offene = "; ".join(
                f"{e.datum} {e.text[:40]} {_eur(e.soll - e.haben)}"
                for e in jk.entries
            )
            findings.append(Finding(
                rule="durchlaufende-posten",
                severity="pruefen",
                title=(
                    f"Konto {jk.nr} {jk.name}: offener Saldo {_eur(abs(jk.saldo))}"
                    f" {'H' if jk.saldo < 0 else 'S'}"
                ),
                detail=f"Durchlaufposten sollten sich ausgleichen. Offene Einzelposten: {offene}.",
                refs=[ref_konto],
            ))

        groups: dict[tuple[str, Decimal, Decimal, str], int] = defaultdict(int)
        for e in jk.entries:
            groups[(e.datum, e.soll, e.haben, e.text)] += 1
        for (d, s, h, t), n in groups.items():
            if n > 1:
                findings.append(Finding(
                    rule="durchlaufende-posten",
                    severity="pruefen",
                    title=f"Konto {jk.nr}: {n}× identische Buchung {d} {_eur(s or h)}",
                    detail=(
                        f"{_LQUOTE}{t}{_RQUOTE} {_DASH} mögliche Doppelbuchung"
                        f" bzw. Sammelzahlung,"
                        f" die auf Einzelrechnungen aufgeteilt werden müsste."
                    ),
                    refs=[ref_konto],
                ))

        old = [
            e for e in jk.entries
            if _pdate(e.datum) and (ref - _pdate(e.datum)).days > max_tage  # type: ignore[operator]
        ]
        if old and abs(jk.saldo) > tol:
            findings.append(Finding(
                rule="durchlaufende-posten",
                severity="info",
                title=f"Konto {jk.nr}: {len(old)} Posten seit mehr als {max_tage} Tagen offen",
                detail="; ".join(
                    f"{e.datum} {e.text[:35]} {_eur(e.soll - e.haben)}" for e in old
                ),
                refs=[ref_konto],
            ))

        for e in jk.entries:
            if "erl" in e.text.lower() and "bitte" in e.text.lower():
                findings.append(Finding(
                    rule="durchlaufende-posten",
                    severity="info",
                    title=f"Konto {jk.nr}: Klärungsvermerk des Steuerberaters",
                    detail=f"{e.datum} {_LQUOTE}{e.text}{_RQUOTE}",
                    refs=[ref_konto],
                ))

    return findings
