"""P3-B migration 010 — events structural fields for V2 (nullable, no backfill,
no regroup of legacy events)."""
import sqlite3


def test_migration_010_adds_structural_columns_preserving_legacy(db):
    from app.db.repo import EventsRepo, utcnow

    db.execute("INSERT INTO events(title,status,first_seen_at,last_seen_at) VALUES"
               "('رویداد قدیمی legacy','PUBLISHED','2030-01-01','2030-01-01')")
    legacy_id = db.query_one("SELECT MAX(id) i FROM events")["i"]
    cols = {r["name"] for r in db.query("PRAGMA table_info(events)")}
    for c in ("fingerprint_json", "event_type", "context_ref", "state", "epoch"):
        assert c in cols, f"migration 010 missing column {c}"
    legacy = db.query_one("SELECT * FROM events WHERE id=?", (legacy_id,))
    assert legacy["title"] == "رویداد قدیمی legacy"  # preserved
    assert legacy["epoch"] is None or legacy["epoch"] == ""  # legacy = pre-V2 epoch


def test_events_table_has_indexes_for_bounded_retrieval(db):
    idx = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_events_v2_retrieval" in idx
