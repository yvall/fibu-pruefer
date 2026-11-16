"""Skill kosten-deckung: Gebuchte Kosten gegen Eingangsbelege auf Summenebene.

Thin Wrapper um legacy check_deckung.
"""
from __future__ import annotations

from fibu.contracts import Context, Finding
from fibu.contracts.finding import Ref
from legacy.fibu_pruefer.belege import check_deckung as _legacy  # type: ignore[import]


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
    return _convert(result, "kosten-deckung")
