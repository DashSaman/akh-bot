"""INCIDENT-2026-10-04 regression: lifecycle edits must NOT consume post caps.

Edits refresh a SENT row's updated_at; sent_since() counted them and the
daily cap (120) filled with edits, throttling every real publication to +1h
reschedules — the channel went quiet. Caps now count first-sends only
(new_posts_since).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.repo import PublicationsRepo

_counter = {"n": 0}


def _sent(db, story_id: int, when: datetime) -> int:
    """Insert one SENT publication row (unique hash) for the story."""
    db.execute(
        "INSERT INTO events(title, status, first_seen_at, last_seen_at)"
        " VALUES ('رخداد', 'NEW', '2030-01-01T00:00:00+00:00', '2030-01-01T00:00:00+00:00')")
    db.execute(
        "INSERT OR IGNORE INTO stories(id, event_id, slug, headline, lead, draft_json,"
        " version, status, created_at, updated_at)"
        " VALUES (?, (SELECT MAX(id) FROM events), ?, 'خبر', 'لید', '{}', 1, 'DRAFT',"
        " '2030-01-01T00:00:00+00:00', '2030-01-01T00:00:00+00:00')",
        (story_id, f"s{story_id}"))
    _counter["n"] += 1
    pubs = PublicationsRepo(db)
    p = pubs.upsert(story_id, "telegram", f"h{_counter['n']}", 1)
    pubs.mark(p, "SENT", remote_id=str(100 + story_id))
    db.execute("UPDATE publications SET updated_at=? WHERE id=?",
               (when.isoformat(timespec="seconds"), p))
    return p


def test_new_posts_since_ignores_edits(db):
    now = datetime.now(timezone.utc)
    # story 1: first send 10h ago, then 50 lifecycle EDITS within the hour
    _sent(db, 1, now - timedelta(hours=10))
    for _ in range(50):
        _sent(db, 1, now - timedelta(minutes=5))
    # story 2: first send 5 minutes ago
    _sent(db, 2, now - timedelta(minutes=5))

    pubs = PublicationsRepo(db)
    assert pubs.sent_since(now - timedelta(hours=24)) >= 51  # old buggy counter
    assert pubs.new_posts_since(now - timedelta(hours=24)) == 2  # first sends only
    # 1h window: story 1's FIRST send was 10h ago (its in-window rows are
    # edits → excluded); only story 2's first send falls inside.
    assert pubs.new_posts_since(now - timedelta(hours=1)) == 1


def test_new_posts_since_window_scoping(db):
    now = datetime.now(timezone.utc)
    _sent(db, 3, now - timedelta(hours=30))   # outside 24h window
    _sent(db, 4, now - timedelta(hours=2))    # inside 24h, outside 1h
    _sent(db, 5, now - timedelta(minutes=10))
    pubs = PublicationsRepo(db)
    assert pubs.new_posts_since(now - timedelta(hours=24)) == 2
    assert pubs.new_posts_since(now - timedelta(hours=1)) == 1
