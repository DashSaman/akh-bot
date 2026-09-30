"""Telegram publisher: idempotency, pause, retry, failure isolation, restart safety."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.core.textnorm import sha256_hex
from app.db.repo import JobsRepo, PublicationsRepo, SettingsRepo, SourcesRepo, StoriesRepo, utcnow
from app.jobs.runner import JobRunner, make_publish_handler
from app.publishing.telegram_bot import TelegramBotPublisher, telegram_text_for_story

DRAFT = {
    "headline": "آزمون انتشار",
    "lead": "خبر آزمونی برای تست نشر",
    "uncertain_facts": ["جزئیات دقیق هنوز روشن نیست"],
    "platform_variants": {"telegram": "خبر آزمونی منتشر شد", "x": "", "threads": "",
                          "instagram_caption": "", "web_extra": ""},
}


def _ok_send(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})


def _fail_send(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": False, "description": "Bad Request: chat not found"})


def _story(db):
    SourcesRepo(db).create(name="s", platform="rss", url="u", status="APPROVED")
    db.execute("INSERT INTO events(title,status,first_seen_at,last_seen_at) VALUES('t','NEW',?,?)",
               (utcnow(), utcnow()))
    return StoriesRepo(db).create(1, "خبر آزمون", "لید آزمون", DRAFT)


def _handler_for(db, settings, transport):
    factory = lambda: TelegramBotPublisher("TOK", "@stage", transport=transport)
    return make_publish_handler(db, settings, factory)


class S:  # minimal settings stub
    max_posts_per_hour = 100
    max_posts_per_day = 100


def test_telegram_text_includes_uncertainty_and_signature():
    text = telegram_text_for_story(DRAFT, "— تست")
    assert "آزمون انتشار" in text
    assert "هنوز تأیید نشده" in text
    assert text.endswith("— تست")


@pytest.mark.asyncio
async def test_publish_once_then_idempotent_retry(db):
    story_id = _story(db)
    transport = httpx.MockTransport(_ok_send)
    handler = _handler_for(db, S(), transport)
    payload = {"story_id": story_id, "platform": "telegram",
               "payload_hash": sha256_hex("t1"), "text": "سلام"}
    assert await handler(payload) is True
    pubs = PublicationsRepo(db).list()
    assert pubs[0]["status"] == "SENT" and pubs[0]["remote_id"] == "42"
    # simulated retry/restart: same payload → no duplicate send, still SENT once
    assert await handler(payload) is True
    assert len(PublicationsRepo(db).list()) == 1
    assert PublicationsRepo(db).sent_since(datetime.now(timezone.utc) - timedelta(hours=1)) == 1


@pytest.mark.asyncio
async def test_publish_failure_retries_via_job_backoff(db):
    story_id = _story(db)
    transport = httpx.MockTransport(_fail_send)
    handler = _handler_for(db, S(), transport)
    payload = {"story_id": story_id, "platform": "telegram",
               "payload_hash": sha256_hex("t2"), "text": "سلام"}
    assert await handler(payload) is False  # failure recorded
    rows = PublicationsRepo(db).list()
    assert rows[0]["status"] == "FAILED"

    # via job runner: failing handler → retry with backoff, then done on success
    runner = JobRunner(db, S())
    jobs = JobsRepo(db)
    text = sha256_hex("t3")
    pubs_repo = PublicationsRepo(db)
    pubs_repo.upsert(story_id, "telegram", text, 1)
    jobs.enqueue("publish_telegram", {"story_id": story_id, "platform": "telegram",
                                      "payload_hash": text, "text": "x"},
                 dedupe_key=f"pub:tg:{story_id}:{text[:16]}")
    ok_transport = httpx.MockTransport(_ok_send)
    runner.register("publish_telegram", _handler_for(db, S(), ok_transport))
    n = await runner.tick()
    assert n == 1
    job = jobs.list()[0]
    assert job["status"] == "done"
    # duplicate enqueue of same dedupe key is dropped
    assert jobs.enqueue("publish_telegram", {}, dedupe_key=f"pub:tg:{story_id}:{text[:16]}") is None


@pytest.mark.asyncio
async def test_pause_blocks_publishing_but_not_collection(db):
    story_id = _story(db)
    SettingsRepo(db).set("pause_platform:telegram", "1")
    transport = httpx.MockTransport(_ok_send)
    handler = _handler_for(db, S(), transport)
    ok = await handler({"story_id": story_id, "platform": "telegram",
                        "payload_hash": sha256_hex("t4"), "text": "x"})
    assert ok is True  # skipped, not failed — and no ledger row is even created while paused
    assert PublicationsRepo(db).list() == []
    # global kill switch
    SettingsRepo(db).set("pause_all", "1")
    ok = await handler({"story_id": story_id, "platform": "telegram",
                        "payload_hash": sha256_hex("t5"), "text": "x"})
    assert ok is True
    assert PublicationsRepo(db).sent_since(datetime.now(timezone.utc) - timedelta(hours=1)) == 0


@pytest.mark.asyncio
async def test_stuck_running_jobs_requeued_after_restart(db):
    jobs = JobsRepo(db)
    jobs.enqueue("x", {})
    row = jobs.claim_due(datetime.now(timezone.utc))[0]
    assert row["status"] == "running"
    requeued = jobs.requeue_running()  # what startup does after a crash
    assert requeued == 1
    assert jobs.list()[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_rate_limit_blocks_excess(db):
    story_id = _story(db)

    class Tight(S):
        max_posts_per_hour = 1
        max_posts_per_day = 100

    handler = _handler_for(db, Tight(), httpx.MockTransport(_ok_send))
    p1 = {"story_id": story_id, "platform": "telegram", "payload_hash": sha256_hex("a"), "text": "x"}
    p2 = {"story_id": story_id, "platform": "telegram", "payload_hash": sha256_hex("b"), "text": "y"}
    assert await handler(p1) is True
    assert await handler(p2) is False  # hourly cap reached → retried later, not dropped
