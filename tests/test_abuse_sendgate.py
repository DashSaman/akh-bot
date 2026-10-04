"""§ABUSE + SEND-TIME re-gate regressions (owner 2026-10-04).

Real fixture: «تنگه صدای بتول زن موشلی میاد» ( tg-relayed gutter talk,
published 17:40Z through a job queued before the gates deployed). Fixes:
(a) profanity/mockery gate, (b) the quality gate re-runs at SEND time so a
job queued under old rules is judged by the CURRENT rules when the worker
picks it up.
"""
from __future__ import annotations

import json

import pytest

from app.jobs.runner import make_send_handler
from app.newsroom.quality_gates import (
    abusive_content, publication_quality_gate)

_TS = "2026-10-04T18:00:00+00:00"
BAD = "تنگه صدای بتول زن موشلی میاد"


def test_real_abusive_fixture_blocked():
    assert abusive_content(BAD) is True
    assert publication_quality_gate(None, BAD, "", 50, 0) == "HOLD_ABUSIVE"


def test_abuse_patterns_and_escape():
    assert abusive_content("این مقام عوضی دوباره حرف زد") is True
    # material context about abuse (not hurling it) still passes
    assert abusive_content("وزیر: اتهام عوضی‌خواندن ما رد شد؛ تحریم جدید") is False


@pytest.mark.asyncio
async def test_send_time_regate_blocks_queued_garbage(db, settings):
    """A story whose job was queued BEFORE the gates existed is blocked at
    SEND time — publisher never reached, event HELD with the reason."""
    db.execute(
        "INSERT INTO events (title, status, verification, importance,"
        " velocity, first_seen_at, last_seen_at)"
        " VALUES (?, 'NEW', 'UNVERIFIED', 0, 1, ?, ?)", (BAD, _TS, _TS))
    eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
    db.execute(
        "INSERT INTO stories (event_id, slug, headline, lead, draft_json,"
        " version, status, lifecycle, created_at, updated_at)"
        " VALUES (?, 'abuse1', ?, 'لید', '{}', 1, 'DRAFT', 'PROVISIONAL',"
        " ?, ?)", (eid, BAD, _TS, _TS))
    sid = db.query_one("SELECT MAX(id) id FROM stories")["id"]

    class NoPub:
        async def send_message(self, text, *a, **k):
            raise AssertionError("abusive story must never reach Telegram")

    handler = make_send_handler(db, settings, lambda: NoPub())
    ok = await handler({
        "story_id": sid, "platform": "telegram", "payload_hash": "ab1",
        "text": BAD, "publication_id": 0})
    assert ok is True  # handled: skipped-by-policy, not a failure
    pub = db.query_one("SELECT status, error FROM publications WHERE"
                       " story_id=? ORDER BY id DESC", (sid,))
    assert pub["status"] == "SKIPPED" and "HOLD_ABUSIVE" in pub["error"]
    ev = db.query_one("SELECT status, quality_hold FROM events WHERE id=?",
                      (eid,))
    assert ev["status"] == "HELD" and ev["quality_hold"] == "HOLD_ABUSIVE"


@pytest.mark.asyncio
async def test_send_time_regate_lets_good_story_pass(db, settings):
    db.execute(
        "INSERT INTO events (title, status, verification, importance,"
        " velocity, first_seen_at, last_seen_at)"
        " VALUES ('خبر خوب', 'NEW', 'UNVERIFIED', 60, 60, ?, ?)", (_TS, _TS))
    eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
    h = "حمله موشکی به پایگاه آمریکایی در عراق گزارش شد"
    db.execute(
        "INSERT INTO stories (event_id, slug, headline, lead, draft_json,"
        " version, status, lifecycle, created_at, updated_at)"
        " VALUES (?, 'good1', ?, 'لید', ?, 1, 'DRAFT', 'PROVISIONAL',"
        " ?, ?)", (eid, h, json.dumps({"details": []}), _TS, _TS))
    sid = db.query_one("SELECT MAX(id) id FROM stories")["id"]

    sent = []

    class OkPub:
        chat_id = "-100test"

        async def send_message(self, text, *a, **k):
            sent.append(text)
            return {"ok": True, "message_id": 42}

    handler = make_send_handler(db, settings, lambda: OkPub())
    await handler({
        "story_id": sid, "platform": "telegram", "payload_hash": "gd1",
        "text": h, "publication_id": 0})
    assert len(sent) == 1  # legit story still publishes
