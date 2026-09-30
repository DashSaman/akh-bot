"""Durable job runner (SQLite outbox). Jobs survive restart; stuck 'running'
jobs are requeued at startup. Handlers are idempotent (ledger-guarded)."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from app.config import Settings
from app.db.database import Database
from app.db.repo import JobsRepo, PublicationsRepo, SettingsRepo, StoriesRepo

log = logging.getLogger("akh.jobs")

Handler = Callable[[dict[str, Any]], Awaitable[bool]]


class JobRunner:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.jobs = JobsRepo(db)
        self.handlers: dict[str, Handler] = {}

    def register(self, job_type: str, handler: Handler) -> None:
        self.handlers[job_type] = handler

    async def tick(self) -> int:
        due = self.jobs.claim_due(datetime.now(timezone.utc))
        for job in due:
            handler = self.handlers.get(job["job_type"])
            try:
                payload = json.loads(job["payload_json"] or "{}")
                if handler is None:
                    raise RuntimeError(f"no handler for {job['job_type']}")
                ok = await handler(payload)
                outcome = self.jobs.finish(job["id"], bool(ok), None if ok else "handler reported failure")
            except Exception as e:  # noqa: BLE001 — job errors are data, not crashes
                log.warning("job %s failed: %s", job["id"], e, extra={"job_id": job["id"]})
                outcome = self.jobs.finish(job["id"], False, str(e)[:500])
            log.info("job %s (%s) -> %s", job["id"], job["job_type"], outcome, extra={"job_id": job["id"]})
        return len(due)

    async def loop(self) -> None:
        JobsRepo(self.db).requeue_running()
        while True:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001
                log.exception("jobs tick crashed; continuing")
            await asyncio.sleep(self.settings.jobs_interval_seconds)


def make_publish_handler(db: Database, settings: Settings,
                         telegram_publisher_factory: Callable[[], Any]) -> Handler:
    """Publishes a story to a platform once (ledger idempotency + pauses + rate limits)."""
    pubs = PublicationsRepo(db)
    stories = StoriesRepo(db)
    app_settings = SettingsRepo(db)

    async def handler(payload: dict[str, Any]) -> bool:
        story_id = int(payload["story_id"])
        platform = str(payload["platform"])
        payload_hash = str(payload["payload_hash"])
        if app_settings.is_paused(platform):
            log.info("publish skipped: paused (%s)", platform, extra={"platform": platform})
            return True  # not a failure; re-run later manually or after unpause via admin
        if pubs.already_sent(story_id, platform, payload_hash):
            return True
        now = datetime.now(timezone.utc)
        if pubs.sent_since(now - timedelta(hours=1)) >= settings.max_posts_per_hour:
            return False  # rate limited: retry later
        if pubs.sent_since(now - timedelta(hours=24)) >= settings.max_posts_per_day:
            return False
        story = stories.get(story_id)
        if not story:
            return True  # story vanished; nothing to do
        pub_id = pubs.upsert(story_id, platform, payload_hash, int(story["version"]))
        text = payload.get("text") or ""
        publisher = telegram_publisher_factory()
        result = await publisher.send_message(text)
        if result["ok"]:
            pubs.mark(pub_id, "SENT", remote_id=str(result.get("message_id", "")))
            stories.mark_published(story_id)
            return True
        pubs.mark(pub_id, "FAILED", error=result.get("error"))
        return False

    return handler
