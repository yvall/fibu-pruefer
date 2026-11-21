from __future__ import annotations

import sqlite3
from pathlib import Path

from fibu.store import LaufStore


def _store() -> LaufStore:
    return LaufStore(Path(":memory:"))


def _lauf(store: LaufStore, lauf_id: str = "lauf-1") -> str:
    store.erstelle_lauf(lauf_id, "/tmp/ordner")
    return lauf_id


# ---------------------------------------------------------------------------
# setze_versand_ok / ist_versand_ok
# ---------------------------------------------------------------------------

def test_versand_ok_initial_false() -> None:
    store = _store()
    lauf_id = _lauf(store)
    assert store.ist_versand_ok(lauf_id) is False


def test_versand_ok_nach_setzen_true() -> None:
    store = _store()
    lauf_id = _lauf(store)
    store.setze_versand_ok(lauf_id)
    assert store.ist_versand_ok(lauf_id) is True


def test_versand_ok_idempotent() -> None:
    store = _store()
    lauf_id = _lauf(store)
    store.setze_versand_ok(lauf_id)
    store.setze_versand_ok(lauf_id)  # zweiter Aufruf kein Fehler
    assert store.ist_versand_ok(lauf_id) is True


def test_versand_ok_unbekannte_lauf_id_false() -> None:
    store = _store()
    assert store.ist_versand_ok("nicht-vorhanden") is False


def test_versand_ok_isoliert_je_lauf() -> None:
    store = _store()
    id1 = _lauf(store, "lauf-1")
    id2 = _lauf(store, "lauf-2")
    store.setze_versand_ok(id1)
    assert store.ist_versand_ok(id1) is True
    assert store.ist_versand_ok(id2) is False


# ---------------------------------------------------------------------------
# Schema-Migration auf bestehender DB (ohne versand_ok-Spalte)
# ---------------------------------------------------------------------------

def test_migration_auf_bestehender_db(tmp_path: Path) -> None:
    db_pfad = tmp_path / "alt.db"

    # DB ohne versand_ok-Spalte anlegen
    conn = sqlite3.connect(str(db_pfad))
    conn.execute("""
        CREATE TABLE laeufe (
            lauf_id TEXT PRIMARY KEY, ordner TEXT NOT NULL,
            gestartet TEXT NOT NULL, geschlossen TEXT,
            status TEXT NOT NULL DEFAULT 'laufend'
        )
    """)
    conn.execute("INSERT INTO laeufe VALUES ('alt-id', '/tmp', '2024-01-01', NULL, 'laufend')")
    conn.commit()
    conn.close()

    # LaufStore öffnet die bestehende DB und migriert sie
    store = LaufStore(db_pfad)
    assert store.ist_versand_ok("alt-id") is False
    store.setze_versand_ok("alt-id")
    assert store.ist_versand_ok("alt-id") is True
