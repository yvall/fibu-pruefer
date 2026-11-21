"""LaufStore: SQLite-Persistenz für Prüfläufe, Kontext und Befunde.

Die Datenbankdatei wird mit Rechten 0600 angelegt (enthält echte Finanzdaten).
"""
from __future__ import annotations

import json
import sqlite3
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fibu.contracts import Context, Finding
from fibu.skills_runtime import SkillResult

from .models import LaufInfo

_SCHEMA = """
CREATE TABLE IF NOT EXISTS laeufe (
    lauf_id    TEXT PRIMARY KEY,
    ordner     TEXT NOT NULL,
    gestartet  TEXT NOT NULL,
    geschlossen TEXT,
    status     TEXT NOT NULL DEFAULT 'laufend',
    versand_ok INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS kontext (
    lauf_id     TEXT PRIMARY KEY,
    kontext_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS findings (
    lauf_id      TEXT PRIMARY KEY,
    findings_json TEXT NOT NULL
);
"""

# Rückwärtskompatible Migrationen für bestehende Datenbanken
_MIGRATIONS = [
    "ALTER TABLE laeufe ADD COLUMN versand_ok INTEGER NOT NULL DEFAULT 0",
]


def _jetzt() -> str:
    return datetime.now(tz=UTC).isoformat()


def _result_to_dict(r: SkillResult) -> dict[str, Any]:
    return {
        "skill_id": r.skill_id,
        "findings": [f.model_dump(mode="json") for f in r.findings],
        "error": r.error,
    }


def _result_from_dict(d: dict[str, Any]) -> SkillResult:
    return SkillResult(
        skill_id=d["skill_id"],
        findings=[Finding.model_validate(f) for f in d["findings"]],
        error=d.get("error"),
    )


class LaufStore:
    """SQLite-Speicher für Prüflauf-Metadaten, Kontext und Befunde."""

    def __init__(self, db_pfad: Path | str) -> None:
        pfad = Path(db_pfad)
        if str(pfad) != ":memory:":
            pfad.parent.mkdir(parents=True, exist_ok=True)
            ist_neu = not pfad.exists()
            self._conn = sqlite3.connect(str(pfad))
            if ist_neu:
                pfad.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
        else:
            self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        for migration in _MIGRATIONS:
            try:
                self._conn.execute(migration)
            except sqlite3.OperationalError:
                pass  # Spalte existiert bereits
        self._conn.commit()

    # ------------------------------------------------------------------
    # Lauf-Lebenszyklus
    # ------------------------------------------------------------------

    def erstelle_lauf(self, lauf_id: str, ordner: str) -> None:
        self._conn.execute(
            "INSERT INTO laeufe (lauf_id, ordner, gestartet, status) VALUES (?, ?, ?, 'laufend')",
            (lauf_id, ordner, _jetzt()),
        )
        self._conn.commit()

    def aktualisiere_status(self, lauf_id: str, status: str) -> None:
        geschlossen = _jetzt() if status in ("abgeschlossen", "fehler") else None
        self._conn.execute(
            "UPDATE laeufe SET status = ?, geschlossen = ? WHERE lauf_id = ?",
            (status, geschlossen, lauf_id),
        )
        self._conn.commit()

    def neuester_offener_lauf(self, ordner: str) -> LaufInfo | None:
        row = self._conn.execute(
            "SELECT * FROM laeufe WHERE ordner = ? AND status IN ('laufend','wartend')"
            " ORDER BY gestartet DESC LIMIT 1",
            (ordner,),
        ).fetchone()
        return _row_zu_laufinfo(row) if row else None

    def setze_versand_ok(self, lauf_id: str) -> None:
        self._conn.execute(
            "UPDATE laeufe SET versand_ok = 1 WHERE lauf_id = ?", (lauf_id,)
        )
        self._conn.commit()

    def ist_versand_ok(self, lauf_id: str) -> bool:
        row = self._conn.execute(
            "SELECT versand_ok FROM laeufe WHERE lauf_id = ?", (lauf_id,)
        ).fetchone()
        return bool(row["versand_ok"]) if row else False

    def alle_laeufe(self, ordner: str) -> list[LaufInfo]:
        rows = self._conn.execute(
            "SELECT * FROM laeufe WHERE ordner = ? ORDER BY gestartet DESC",
            (ordner,),
        ).fetchall()
        return [_row_zu_laufinfo(r) for r in rows]

    # ------------------------------------------------------------------
    # Kontext (Context → JSON → Context)
    # ------------------------------------------------------------------

    def speichere_kontext(self, lauf_id: str, ctx: Context) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO kontext (lauf_id, kontext_json) VALUES (?, ?)",
            (lauf_id, ctx.model_dump_json()),
        )
        self._conn.commit()

    def lade_kontext(self, lauf_id: str) -> Context:
        row = self._conn.execute(
            "SELECT kontext_json FROM kontext WHERE lauf_id = ?", (lauf_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Kein Kontext für Lauf {lauf_id!r}")
        return Context.model_validate_json(row["kontext_json"])

    # ------------------------------------------------------------------
    # Findings (list[SkillResult] → JSON → list[SkillResult])
    # ------------------------------------------------------------------

    def speichere_findings(self, lauf_id: str, results: list[SkillResult]) -> None:
        payload = json.dumps([_result_to_dict(r) for r in results], ensure_ascii=False)
        self._conn.execute(
            "INSERT OR REPLACE INTO findings (lauf_id, findings_json) VALUES (?, ?)",
            (lauf_id, payload),
        )
        self._conn.commit()

    def lade_findings(self, lauf_id: str) -> list[SkillResult]:
        row = self._conn.execute(
            "SELECT findings_json FROM findings WHERE lauf_id = ?", (lauf_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Keine Findings für Lauf {lauf_id!r}")
        return [_result_from_dict(d) for d in json.loads(row["findings_json"])]

    def close(self) -> None:
        self._conn.close()


def _row_zu_laufinfo(row: sqlite3.Row) -> LaufInfo:
    geschlossen = row["geschlossen"]
    return LaufInfo(
        lauf_id=row["lauf_id"],
        ordner=row["ordner"],
        gestartet=datetime.fromisoformat(row["gestartet"]),
        geschlossen=datetime.fromisoformat(geschlossen) if geschlossen else None,
        status=row["status"],
    )
