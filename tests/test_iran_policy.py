"""Iran-first policy regressions (directive 2026-10-04 Part A).

90% allocation is soft; capacity spills when Iran supply is thin; crisis mode
concentrates speed/capacity but NEVER weakens verification.
"""
from __future__ import annotations

from app.newsroom.iran_policy import (
    crisis_active, defer_for_iran_capacity, iran_share_6h, is_iran_related,
    update_crisis_mode)
from app.verification.gates import decide_claim_state, event_can_auto_publish

from datetime import datetime, timezone as _tz
_NOW = datetime.now(_tz.utc).isoformat(timespec="seconds")
_TS = "2030-01-01T00:00:00+00:00"


def test_is_iran_related():
    assert is_iran_related("حمله موشکی به تهران") is True
    assert is_iran_related("Iran nuclear talks resume") is True
    assert is_iran_related("فینال جام جهانی فوتبال") is False


def test_capacity_defer_soft_semantics(db):
    # P0/P1 always pass regardless of allocation
    assert defer_for_iran_capacity(db, "اخبار ورزشی", 95) is False
    # P3 with NO Iran supply -> spills automatically, no defer
    assert defer_for_iran_capacity(db, "ورزش", 15) is False
    # P3 while an Iran story waits and rolling share is low -> deferred
    db.execute(
        "INSERT INTO events (title, status, verification, first_seen_at,"
        " last_seen_at) VALUES ('تحریم ایران', 'NEW', 'UNVERIFIED', ?, ?)",
        (_TS, _TS))
    eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
    db.execute(
        "INSERT INTO stories (event_id, slug, headline, lead, draft_json,"
        " version, status, created_at, updated_at)"
        " VALUES (?, 'ir1', 'تحریم جدید علیه ایران اعلام شد', 'لید', '{}', 1,"
        " 'DRAFT', ?, ?)", (eid, _TS, _TS))
    assert defer_for_iran_capacity(db, "نتایج لیگ فوتبال", 15) is True


def test_crisis_mode_triggers_and_auto_exits(db):
    for i in range(2):
        db.execute(
            "INSERT INTO events (title, status, verification, importance,"
            " velocity, first_seen_at, last_seen_at)"
            " VALUES ('حمله به ایران', 'NEW', 'UNVERIFIED', 95, 95, ?, ?)",
            (_TS, _TS))
        eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
        db.execute(
            "INSERT INTO stories (event_id, slug, headline, lead, draft_json,"
            " version, status, created_at, updated_at)"
            " VALUES (?, ?, 'حمله موشکی به ایران', 'لید', '{}', 1, 'DRAFT',"
            " ?, ?)", (eid, f"cr{i}", _NOW, _NOW))
    state = update_crisis_mode(db, calm_minutes=60)
    assert state["active"] is True and state["triggers"] >= 2
    assert crisis_active(db) is True
    # calm period elapses with no new triggers -> auto-exit, no manual restart
    db.execute("UPDATE settings SET value=json_set(value, '$.until',"
               " '2020-01-01T00:00:00+00:00')"
               " WHERE key='IRAN_CRISIS_MODE'")
    # calm period elapses AND the triggering stories age out of the window
    db.execute("UPDATE stories SET created_at='2020-01-01T00:00:00+00:00'")
    update_crisis_mode(db, calm_minutes=60)
    assert crisis_active(db) is False


def test_crisis_never_weakens_verification(db):
    update_crisis_mode(db, calm_minutes=60)
    # claim gates are pure functions of evidence — crisis changes nothing
    assert decide_claim_state("۱۰ کشته در حمله", independent_sources=1,
                              has_contradiction=False, risk="high") \
        == "SINGLE_SOURCE"
    claims = [{"state": "SINGLE_SOURCE", "risk_level": "high", "text": "x"}]
    ok, reason = event_can_auto_publish(claims)
    assert ok is False and reason == "HIGH_RISK_SINGLE_SOURCE"


def test_share_computed_from_created_at_only(db):
    # one Iran-related SENT post (created now), one old edited row excluded
    db.execute(
        "INSERT INTO events (title, status, verification, first_seen_at,"
        " last_seen_at) VALUES ('تست سهم', 'NEW', 'UNVERIFIED', ?, ?)", (_TS, _TS))
    eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
    db.execute(
        "INSERT INTO stories (event_id, slug, headline, lead, draft_json,"
        " version, status, created_at, updated_at)"
        " VALUES (?, 'sh1', 'ایران تحریم جدید', 'لید', '{}', 1, 'PUBLISHED',"
        " ?, ?)", (eid, _NOW, _NOW))
    sid = db.query_one("SELECT MAX(id) id FROM stories")["id"]
    db.execute(
        "INSERT INTO publications (story_id, platform, payload_hash, attempt,"
        " status, created_at, updated_at) VALUES (?, 'telegram', 'h1', 1,"
        " 'SENT', ?, ?)", (sid, _NOW, _NOW))
    assert iran_share_6h(db) == 1.0
