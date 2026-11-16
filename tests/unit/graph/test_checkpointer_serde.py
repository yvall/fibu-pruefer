"""Serialisierungstest: Decimal und str überleben den MemorySaver-Roundtrip."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver

from fibu.contracts import Calc, Finding, Ref
from fibu.graph.runner import run_pruefung
from fibu.skills_runtime import SkillResult
from fibu.store import LaufStore


def _decimal_finding() -> Finding:
    return Finding(
        rule="serde-test",
        severity="fehler",
        title="Betrag-Differenz",
        detail="D",
        calc=Calc(
            erwartet=Decimal("12345.67"),
            ist=Decimal("12300.00"),
            differenz=Decimal("45.67"),
            formel="Konten 44xx",
        ),
        refs=[Ref(art="konto", id="4400")],
    )


def test_decimal_in_skill_results_roundtrip(make_context: Any, tmp_path: Path) -> None:
    """skill_results mit Decimal-Feldern bleiben nach Graph-Durchlauf korrekt."""
    store = LaufStore(Path(":memory:"))
    ctx = make_context()
    finding = _decimal_finding()

    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills",
              return_value=[SkillResult(skill_id="x", findings=[finding])]),
    ):
        result = run_pruefung(
            tmp_path, mit_mail=False, store=store, _checkpointer=MemorySaver()
        )

    results = result["skill_results"]
    assert len(results) >= 1
    f_roundtrip = results[0].findings[0]
    assert isinstance(f_roundtrip.calc.erwartet, Decimal)  # type: ignore[union-attr]
    assert f_roundtrip.calc.erwartet == Decimal("12345.67")  # type: ignore[union-attr]


def test_bericht_pfad_als_str_im_state(make_context: Any, tmp_path: Path) -> None:
    """bericht_md_pfad ist ein str (nicht Path) – kompatibel mit SqliteSaver."""
    store = LaufStore(Path(":memory:"))
    ctx = make_context()

    with (
        patch("fibu.graph.nodes.load_context", return_value=ctx),
        patch("fibu.graph.nodes.run_skills", return_value=[]),
    ):
        result = run_pruefung(
            tmp_path, mit_mail=False, store=store, _checkpointer=MemorySaver()
        )

    assert isinstance(result["bericht_md_pfad"], str)
    assert isinstance(result["bericht_html_pfad"], str)
