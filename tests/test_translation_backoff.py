"""THRASH-FIX regression: translation retry backoff + per-pass budget.

Held NEEDS_LANGUAGE_PROCESSING events used to retry every pipeline pass
(~3min), exhausting the free-tier AI pool and starving the backlog.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.newsroom.v2_pipeline import (
    _TRANSLATE_BUDGET_PER_PASS,
    _record_translation_outcome,
    _translation_gate,
)


def _mk_event(db) -> int:
    db.execute(
        "INSERT INTO events (title, category, status, importance, velocity, "
        "verification, report_count, independent_count, first_seen_at, last_seen_at) "
        "VALUES ('טקסט עברי לבדיקה', 'conflict', 'HELD', 50, 0, 'UNVERIFIED', 1, 0, "
        "'2030-01-01T00:00:00+00:00', '2030-01-01T00:00:00+00:00')")
    row = db.execute("SELECT MAX(id) m FROM events").fetchone()
    return row["m"]


def test_gate_allows_fresh_event(db):
    eid = _mk_event(db)
    assert _translation_gate(db, eid, {}) is None


def test_gate_blocks_inside_backoff_window(db):
    eid = _mk_event(db)
    _record_translation_outcome(db, eid, ok=False)
    row = db.execute("SELECT translate_attempts a, next_translate_at n FROM events WHERE id=?",
                     (eid,)).fetchone()
    assert row["a"] == 1
    assert row["n"]  # a future retry time is set
    assert _translation_gate(db, eid, {}) == "backoff"


def test_gate_blocks_when_budget_spent(db):
    eid = _mk_event(db)
    summary = {"translations": _TRANSLATE_BUDGET_PER_PASS}
    assert _translation_gate(db, eid, summary) == "budget"
    # budget caps even a fresh event with no backoff set
    assert db.execute("SELECT next_translate_at n FROM events WHERE id=?",
                      (eid,)).fetchone()["n"] == ""


def test_backoff_doubles_and_caps(db):
    eid = _mk_event(db)
    for _ in range(6):
        _record_translation_outcome(db, eid, ok=False)
    row = db.execute("SELECT translate_attempts a, next_translate_at n FROM events WHERE id=?",
                     (eid,)).fetchone()
    assert row["a"] == 6
    nxt = datetime.strptime(row["n"], "%Y-%m-%dT%H:%M:%S")
    delta = nxt - datetime.utcnow()
    # 6th failure: min(300*2^5, 3600) = 3600s cap
    assert timedelta(minutes=55) < delta <= timedelta(hours=1, minutes=2)


def test_success_resets_backoff(db):
    eid = _mk_event(db)
    _record_translation_outcome(db, eid, ok=False)
    _record_translation_outcome(db, eid, ok=True)
    row = db.execute("SELECT translate_attempts a, next_translate_at n FROM events WHERE id=?",
                     (eid,)).fetchone()
    assert row["a"] == 0 and row["n"] == ""
    assert _translation_gate(db, eid, {}) is None
