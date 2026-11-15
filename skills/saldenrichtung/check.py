"""Skill saldenrichtung: Saldenrichtung und negative Monatssummen prüfen."""
from __future__ import annotations

from decimal import Decimal

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Ref

ZERO = Decimal(0)

# SKR04-Kontenklassen → erwartetes Vorzeichen (+1 = Soll, -1 = Haben)
_EXPECT: dict[str, int] = {"0": 1, "1": 1, "3": -1, "4": -1, "6": 1, "7": 1}

_DEFAULT_SKIP = ["2910", "3820", "3830", "4946", "1370", "6850_"]


def _eur(val: Decimal) -> str:
    s = f"{val:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def run(ctx: Context) -> list[Finding]:
    a = ctx.auswertung
    min_saldo = Decimal(str(ctx.config.get("saldenrichtung_min_saldo", "1.00")))
    raw_skip = ctx.config.get("saldenrichtung_skip", _DEFAULT_SKIP)
    skip: set[str] = set(raw_skip) if isinstance(raw_skip, (list, set)) else set(_DEFAULT_SKIP)

    findings: list[Finding] = []

    # 1. Erwartete Saldenrichtung (Sachkonten ≤ 4 Stellen)
    for n, k in a.sus.items():
        if len(n) > 4 or n in skip:
            continue
        exp = _EXPECT.get(n[0])
        if exp and abs(k.saldo) >= min_saldo and (k.saldo > 0) != (exp > 0):
            side = "Haben" if k.saldo < 0 else "Soll"
            findings.append(
                Finding(
                    rule="saldenrichtung",
                    severity="pruefen",
                    title=f"Konto {n} {k.name}: ungewöhnlicher {side}-Saldo",
                    detail=(
                        f"Saldo {_eur(abs(k.saldo))} {side[0]},"
                        f" erwartet wäre die Gegenseite."
                        f" Bitte Kontierung/Gegenbuchung prüfen."
                    ),
                    refs=[Ref(art="konto", id=n, label=k.name)],
                )
            )

    # 2. Negative Monatssummen (alle Konten)
    for n, k in a.sus.items():
        if k.per_soll < 0 or k.per_haben < 0:
            findings.append(
                Finding(
                    rule="saldenrichtung",
                    severity="info",
                    title=f"Konto {n} {k.name}: negative Monatssumme",
                    detail=(
                        f"Soll {_eur(k.per_soll)} / Haben {_eur(k.per_haben)}"
                        f" – deutet auf Storno/Gegenbuchung hin."
                    ),
                    refs=[Ref(art="konto", id=n, label=k.name)],
                )
            )

    # 3. Personenkonten falsche Seite
    for n, k in a.sus.items():
        if (
            len(n) == 5
            and n.startswith(("1", "7"))
            and abs(k.saldo) >= min_saldo
            and (n.startswith("1") != (k.saldo > 0))
        ):
            findings.append(
                Finding(
                    rule="saldenrichtung",
                    severity="pruefen",
                    title=f"Personenkonto {n} {k.name}: Saldo auf der „falschen“ Seite",
                    detail=f"Saldo {_eur(k.saldo)} (Soll +, Haben −).",
                    refs=[Ref(art="konto", id=n, label=k.name)],
                )
            )

    return findings
