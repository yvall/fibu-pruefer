"""Skill belege-abgleich: Belege & Gutschriften gegen offene Posten abgleichen.

Thin Wrapper um legacy check_belege. BelegRecord duck-typed als Beleg –
beide haben identische Felder und Properties (.norm, .primary, .brutto …).
"""
from __future__ import annotations

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Ref
from legacy.fibu_pruefer.belege import check_belege as _legacy  # type: ignore[import]


def _convert(result: object, rule_id: str) -> list[Finding]:
    return [
        Finding(
            rule=rule_id,
            severity=f.severity,
            title=f.title,
            detail=f.detail,
            refs=[Ref(art="beleg", id=f.ref)] if getattr(f, "ref", "") else [],
        )
        for f in getattr(result, "findings", [])
    ]


def run(ctx: Context) -> list[Finding]:
    result = _legacy(ctx.auswertung, ctx.belege)
    return _convert(result, "belege-abgleich")
