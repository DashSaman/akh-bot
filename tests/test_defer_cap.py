"""§DEFER-CAP regressions: soft deferrals (diversity / Iran allocation) are
BOUNDED — a story older than 20 minutes publishes regardless, so fairness
can never suppress fresh news into an infinite retry loop.

Regression for the 2026-10-04 evening stall: 42 fresh items arrived in 90
minutes and produced 0 new stories because every pipeline pass re-deferred
the same stories while the allocation condition held.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.newsroom.v2_pipeline import _defer_cap_reached

_NOW = datetime.now(timezone.utc)


def test_fresh_story_can_still_be_deferred(db):
    db.execute(
        "INSERT INTO events (title, status, verification, first_seen_at,"
        " last_seen_at) VALUES ('تازه', 'NEW', 'UNVERIFIED', ?, ?)",
        ((_NOW - timedelta(minutes=3)).isoformat(timespec="seconds"),) * 2)
    eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
    assert _defer_cap_reached(db, eid) is False


def test_stale_deferred_story_publishes_anyway(db):
    db.execute(
        "INSERT INTO events (title, status, verification, first_seen_at,"
        " last_seen_at) VALUES ('قدیمی', 'READY', 'UNVERIFIED', ?, ?)",
        ((_NOW - timedelta(minutes=25)).isoformat(timespec="seconds"),) * 2)
    eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
    assert _defer_cap_reached(db, eid) is True


def test_empty_timestamp_never_defers(db):
    db.execute(
        "INSERT INTO events (title, status, verification, first_seen_at,"
        " last_seen_at) VALUES ('بدون‌زمان', 'NEW', 'UNVERIFIED', '', '')")
    eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
    assert _defer_cap_reached(db, eid) is True
