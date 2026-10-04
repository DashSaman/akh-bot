"""§BLACKHOLE regressions: unrelated claims must NEVER attach to an event.

2026-10-04 stall root cause: _find_same_claim_event attached on
POTENTIAL_CONTRADICTION, which fires on ACTOR_DIFFERS alone for any two
actor-bearing claims — rich-get-richer mega-events (620/347/301 items)
swallowed the stream and nothing published.
"""
from __future__ import annotations

from app.newsroom.claim_model import StructuredClaim
from app.newsroom.v2_pipeline import _find_same_claim_event


def _claim(text, actor="", **kw):
    from app.newsroom.claim_model import ClaimClass
    kw.setdefault("claim_class", ClaimClass.GENERAL)
    kw.setdefault("source_item_id", 1)
    return StructuredClaim(text=text, actor=actor, **kw)


def _seed(db, text, actor=""):
    db.execute(
        "INSERT INTO events (title, status, verification, first_seen_at,"
        " last_seen_at) VALUES (?, 'NEW', 'UNVERIFIED', '2030-01-01T00:00:00+00:00',"
        " '2030-01-01T00:00:00+00:00')", (text[:60],))
    eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
    db.execute(
        "INSERT INTO claims (event_id, text, actor, state, risk_level,"
        " fingerprint, created_at, updated_at) VALUES (?, ?, ?, 'UNVERIFIED',"
        " 'normal', '', '2030-01-01T00:00:00+00:00', '2030-01-01T00:00:00+00:00')",
        (eid, text, actor))
    return eid


def test_unrelated_actors_do_not_attach(db):
    eid = _seed(db, "وزیر کشور پاکستان از حمله خبر داد", actor="وزیر کشور پاکستان")
    db.execute("UPDATE claims SET actor=? WHERE event_id=?", ("وزیر کشور پاکستان", eid))
    fresh = _claim("DeepSeek and Huawei take aim at Nvidia formidable moat",
                   actor="DeepSeek")
    assert _find_same_claim_event(db, fresh, "2030-01-01T00:05:00+00:00") is None


def test_same_subject_conflicting_number_attaches(db):
    eid = _seed(db, "حمله موشکی به پایگاه عین الاسد ۱۰ کشته بر جای گذاشت")
    fresh = _claim("حمله موشکی به پایگاه عین الاسد ۱۲ کشته بر جای گذاشت")
    got = _find_same_claim_event(db, fresh, "2030-01-01T00:05:00+00:00")
    assert got == eid  # same story, conflicting detail -> same event


def test_paraphrase_attaches(db):
    eid = _seed(db, "ارتش آمریکا پایگاه جدیدی در عراق ساخت",
                actor="ارتش آمریکا")
    fresh = _claim("ارتش آمریکا پایگاه تازه‌ای در عراق ساخت",
                   actor="ارتش آمریکا")
    got = _find_same_claim_event(db, fresh, "2030-01-01T00:05:00+00:00")
    assert got == eid
