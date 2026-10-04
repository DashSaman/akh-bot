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


class Throttled(Exception):
    """Rate-cap reached: the job must be RESCHEDULED to the next eligible
    time without consuming a failure retry (URGENT-FIX §3)."""

    def __init__(self, retry_in_seconds: float = 120.0):
        super().__init__(f"rate cap; retry in {retry_in_seconds:.0f}s")
        self.retry_in_seconds = retry_in_seconds



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
                try:
                    # STALL-RECOVERY (2026-10-04 incident): a hung network
                    # call inside a handler froze the whole jobs loop for
                    # hours. Every handler is bounded; a timeout counts as a
                    # normal failure retry, never a loop freeze.
                    ok = await asyncio.wait_for(
                        handler(payload),
                        timeout=float(getattr(self.settings, "job_handler_timeout_seconds", 180)))
                except Throttled as th:
                    from datetime import timedelta as _td
                    self.jobs.reschedule(
                        job["id"],
                        datetime.now(timezone.utc) + _td(seconds=th.retry_in_seconds))
                    log.info("job %s THROTTLED (rate cap) — rescheduled", job["id"],
                             extra={"job_id": job["id"]})
                    continue
                except asyncio.TimeoutError:
                    raise RuntimeError(
                        f"handler timeout after "
                        f"{getattr(self.settings, 'job_handler_timeout_seconds', 180)}s")
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


def lifecycle_now(story) -> str:
    return (story.get("lifecycle") if isinstance(story, dict) else None) or "CONFIRMED"


def _resolve_media_ref(db, story_id: int) -> dict | None:
    """Publishable ORIGINAL asset for the story, resolved at SEND time
    (FINAL MEDIA: file_id/URL ladder; no frozen paths, no generated cards)."""
    from app.publishing import media as _media_mod

    best = _media_mod.best_for_story(db, story_id)
    if not best:
        return None
    return {"asset_id": best["id"],
            "file_id": best["telegram_file_id"] or "",
            "url": best["remote_url"] or "",
            "video": best["kind"] == "video"}


def _policy_blocked(db: Database, settings: Settings, story_id: int,
                    platform: str, payload_hash: str, pubs, stories) -> str | None:
    """Execution-time checks shared by all publish handlers: story existence,
    pause, and the CURRENT source allowlist / publication policy. Returns a
    skip reason or None. An old queued job must never bypass current policy."""
    story = stories.get(story_id)
    if not story:
        return "NO_STORY"
    app_settings = SettingsRepo(db)
    if app_settings.is_paused(platform):
        return "PAUSED"
    ev = db.query_one("SELECT * FROM events WHERE id=?", (story["event_id"],))
    if ev:
        origin = db.query(
            "SELECT DISTINCT s.enabled en, s.source_control_state scs,"
            " s.publication_policy pp FROM event_items ei"
            " JOIN raw_items r ON r.id=ei.raw_item_id"
            " JOIN sources s ON s.id=r.source_id"
            " WHERE ei.event_id=? AND ei.is_duplicate=0", (story["event_id"],))
        if origin and not any(o["en"] and o["scs"] == "OWNER_ENABLED" and o["pp"] == "AUTO" for o in origin):
            pubs.mark(pubs.upsert(story_id, platform, payload_hash, int(story["version"])),
                      "SKIPPED", error="CANCELLED_SOURCE_DISABLED")
            return "CANCELLED_SOURCE_DISABLED"
    return None


def _sent_in_current_chat(db, settings, story_id: int, platform: str) -> dict | None:
    current_chat = getattr(settings, "telegram_publish_target", "") if platform == "telegram" else ""
    prior = db.query_one(
        "SELECT * FROM publications WHERE story_id=? AND platform=? AND status='SENT' "
        "ORDER BY id DESC LIMIT 1", (story_id, platform))
    if prior and prior.get("remote_id") and (
            not current_chat or not prior.get("chat_id") or prior["chat_id"] == str(current_chat)):
        return prior
    return None


def make_send_handler(db: Database, settings: Settings,
                      telegram_publisher_factory: Callable[[], Any]) -> Handler:
    """P3-E publish_send: FIRST publication of a story. HARD INVARIANT (§21):
    an existing SENT publication for (story, platform) makes SEND forbidden —
    updates must go through publish_edit. Fail-closed, ledger-guarded."""
    pubs = PublicationsRepo(db)
    stories = StoriesRepo(db)

    async def handler(payload: dict[str, Any]) -> bool:
        story_id = int(payload["story_id"])
        platform = str(payload["platform"])
        payload_hash = str(payload["payload_hash"])
        blocked = _policy_blocked(db, settings, story_id, platform, payload_hash, pubs, stories)
        if blocked == "NO_STORY":
            return True
        if blocked:
            return True
        story = stories.get(story_id)
        if pubs.already_sent(story_id, platform, payload_hash):
            return True
        # THE invariant: never SEND a second post for an already-published story
        if _sent_in_current_chat(db, settings, story_id, platform) is not None:
            pubs.mark(pubs.upsert(story_id, platform, payload_hash, int(story["version"])),
                      "SKIPPED", error="SEND_FORBIDDEN_EDIT_ONLY")
            log.warning("publish_send forbidden (SENT exists) story %s", story_id)
            return True
        # FRESHNESS GATE: stale backlog must not flood the channel later.
        ev = db.query_one("SELECT * FROM events WHERE id=?", (story["event_id"],))
        if ev:
            from datetime import timezone as _tz
            age_min = None
            for stamp in (ev["last_seen_at"], story["created_at"]):
                try:
                    dt = datetime.fromisoformat(stamp)
                    age_min = (datetime.now(_tz.utc) - dt).total_seconds() / 60
                    break
                except (TypeError, ValueError):
                    continue
            max_age = float(getattr(settings, "standard_max_age_minutes", 180))
            if age_min is not None and age_min > max_age and lifecycle_now(story) in ("CONFIRMED",):
                pubs.mark(pubs.upsert(story_id, platform, payload_hash, int(story["version"])),
                          "SKIPPED", error="STALE_SUPERSEDED")
                return True
        # SEND-TIME quality re-gate: a job queued BEFORE a gate update is
        # still judged by the CURRENT public-quality rules at send time
        # (owner 2026-10-04: the «بتول زن موشلی» post raced through this way)
        from app.newsroom.quality_gates import publication_quality_gate
        from app.verification.gates import classify_priority
        _tw2, _w2 = classify_priority(str(story["headline"] or ""))
        _body2 = ""
        try:
            import json as _json2
            _d = _json2.loads(story["draft_json"] or "{}")
            _body2 = " ".join(_d.get("details") or [])
        except Exception:  # noqa: BLE001
            _body2 = ""
        _qreason = publication_quality_gate(
            db, str(story["headline"] or ""), _body2, _w2,
            event_id=story["event_id"])
        if _qreason:
            pubs.mark(pubs.upsert(story_id, platform, payload_hash,
                                  int(story["version"])), "SKIPPED",
                      error=f"QUALITY_{_qreason}")
            try:
                from app.db.repo import EventsRepo as _ER
                _ER(db).set_quality_hold(story["event_id"], _qreason)
            except Exception:  # noqa: BLE001 — non-fatal bookkeeping
                log.exception("send-time gate hold bookkeeping failed")
            log.warning("publish_send quality-blocked at SEND time story=%s"
                        " reason=%s", story_id, _qreason)
            return True
        lifecycle = story.get("lifecycle") or "CONFIRMED"
        cap = (getattr(settings, "max_provisional_posts_per_hour", 6)
               if lifecycle == "PROVISIONAL"
               else getattr(settings, "max_confirmed_posts_per_hour", 12))
        now = datetime.now(timezone.utc)
        # URGENT-FIX §3: a rate-capped publication is THROTTLED — rescheduled
        # to the next eligible window; it NEVER consumes failure retries and
        # NEVER becomes permanently FAILED merely because of the cap.
        # INCIDENT-2026-10-04: caps count NEW posts only (new_posts_since);
        # lifecycle edits refresh a SENT row's updated_at but add no channel
        # message — counting them starved publishing once edits pushed
        # sent_24h to the daily cap.
        sent_1h = pubs.new_posts_since(now - timedelta(hours=1))
        sent_24h = pubs.new_posts_since(now - timedelta(hours=24))
        if sent_1h >= min(cap, getattr(settings, "max_posts_per_hour", 12))                 or sent_24h >= getattr(settings, "max_posts_per_day", 120):
            # next eligible: when the oldest first-send ages out of the window
            oldest = db.query_one(
                "SELECT MIN(p.updated_at) AS t FROM publications p WHERE p.status='SENT'"
                " AND p.updated_at>=? AND NOT EXISTS ("
                "  SELECT 1 FROM publications q WHERE q.story_id=p.story_id"
                "  AND q.status='SENT' AND q.id<p.id)",
                ((now - timedelta(hours=24)).isoformat(timespec="seconds"),))
            retry_in = 300.0
            if sent_24h >= getattr(settings, "max_posts_per_day", 120):
                retry_in = 3600.0
            elif oldest and oldest.get("t"):
                try:
                    from datetime import datetime as _dt
                    t0 = _dt.fromisoformat(str(oldest["t"]).replace("Z", "+00:00"))
                    retry_in = max(60.0, min(3600.0, (now - t0).total_seconds()))
                except ValueError:
                    pass
            raise Throttled(retry_in)
        text = payload.get("text") or ""
        # URGENT-FIX §5: fail-closed final body gate (screenshot regression)
        from app.publishing.telegram_bot import public_body_is_substantive
        if text and not public_body_is_substantive(text):
            pubs.mark(pubs.upsert(story_id, platform, payload_hash,
                                  int(story["version"])),
                      "SKIPPED", error="BLOCKED_BODY_GATE")
            log.warning("publish_send blocked: non-substantive body (story %s)", story_id)
            return True
        publisher = telegram_publisher_factory()
        # FINAL MEDIA ladder: Telegram file_id → public source URL → bounded
        # temp download (deleted after) → text-only. NEVER a generated card.
        from app.publishing import media as _media_mod
        media_ref = _resolve_media_ref(db, story_id)
        legacy_path = str(payload.get("media_path") or "")
        if media_ref is not None and (media_ref.get("file_id") or media_ref.get("url")):
            if _media_mod.media_downloads_allowed(db):
                downloader = (lambda u, sid=story_id: _media_mod.download_to_temp(u, sid))
            else:
                downloader = None
            result = await publisher.send_media_ref(
                media_ref, text, video=bool(media_ref.get("video")),
                downloader=downloader)
            if result.get("ok") and result.get("file_id"):
                _media_mod.set_telegram_file_id(db, int(media_ref.get("asset_id") or 0),
                                                result["file_id"])
        elif legacy_path:
            result = await publisher.send_media(legacy_path, text)
        else:
            result = await publisher.send_message(text)
        pub_id = pubs.upsert(story_id, platform, payload_hash, int(story["version"]))
        db.execute("UPDATE publications SET chat_id=? WHERE id=?", (str(publisher.chat_id), pub_id))
        if result["ok"]:
            pubs.mark(pub_id, "SENT", remote_id=str(result.get("message_id", "")))
            stories.mark_published(story_id)
            return True
        pubs.mark(pub_id, "FAILED", error=result.get("error"))
        return False

    return handler


def make_edit_handler(db: Database, settings: Settings,
                      telegram_publisher_factory: Callable[[], Any]) -> Handler:
    """P3-E publish_edit: updates an ALREADY-SENT story by editing the SAME
    Telegram message. NEVER sends: no SENT target ⇒ skip (a first publication
    is publish_send's job). Fail-closed language gate inside the publisher."""
    pubs = PublicationsRepo(db)
    stories = StoriesRepo(db)

    async def handler(payload: dict[str, Any]) -> bool:
        story_id = int(payload["story_id"])
        platform = str(payload["platform"])
        payload_hash = str(payload["payload_hash"])
        blocked = _policy_blocked(db, settings, story_id, platform, payload_hash, pubs, stories)
        if blocked == "NO_STORY":
            return True
        if blocked:
            return True
        prior = _sent_in_current_chat(db, settings, story_id, platform)
        if prior is None:
            pubs.mark(pubs.upsert(story_id, platform, payload_hash,
                                  int(stories.get(story_id)["version"])),
                      "SKIPPED", error="NO_SENT_TARGET_TO_EDIT")
            log.warning("publish_edit skipped: no SENT target (story %s)", story_id)
            return True
        etext = payload.get("text") or ""
        from app.publishing.telegram_bot import public_body_is_substantive
        if etext and not public_body_is_substantive(etext):
            pubs.mark(pubs.upsert(story_id, platform, payload_hash,
                                  int(stories.get(story_id)["version"])),
                      "SKIPPED", error="BLOCKED_BODY_GATE")
            log.warning("publish_edit blocked: non-substantive body (story %s)", story_id)
            return True
        publisher = telegram_publisher_factory()
        result = await publisher.edit_message(prior["remote_id"], payload.get("text") or "")
        pub_id = pubs.upsert(story_id, platform, payload_hash,
                             int(stories.get(story_id)["version"]))
        db.execute("UPDATE publications SET chat_id=? WHERE id=?", (str(publisher.chat_id), pub_id))
        if result["ok"]:
            pubs.mark(pub_id, "SENT", remote_id=str(prior["remote_id"]))
            stories.mark_published(story_id)
            return True
        pubs.mark(pub_id, "FAILED", error=result.get("error"))
        return False

    return handler


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
            return True
        story = stories.get(story_id)
        if not story:
            return True

        # EXECUTION-TIME policy recheck: an old queued job must not bypass the
        # CURRENT source allowlist / publication policy.
        ev = db.query_one("SELECT * FROM events WHERE id=?", (story["event_id"],))
        if ev:
            origin = db.query(
                "SELECT DISTINCT s.enabled en, s.source_control_state scs,"
                " s.publication_policy pp FROM event_items ei"
                " JOIN raw_items r ON r.id=ei.raw_item_id"
                " JOIN sources s ON s.id=r.source_id"
                " WHERE ei.event_id=? AND ei.is_duplicate=0", (story["event_id"],))
            if origin and not any(o["en"] and o["scs"] == "OWNER_ENABLED" and o["pp"] == "AUTO" for o in origin):
                pubs.mark(pubs.upsert(story_id, platform, payload_hash, int(story["version"])),
                          "SKIPPED", error="CANCELLED_SOURCE_DISABLED")
                log.info("publish cancelled at execution: source disabled/policy (story %s)", story_id)
                return True

        # FRESHNESS GATE: stale backlog must not flood the channel later.
        ev = db.query_one("SELECT * FROM events WHERE id=?", (story["event_id"],))
        if ev:
            from datetime import timezone as _tz
            age_min = None
            for stamp in (ev["last_seen_at"], story["created_at"]):
                try:
                    dt = datetime.fromisoformat(stamp)
                    age_min = (datetime.now(_tz.utc) - dt).total_seconds() / 60
                    break
                except (TypeError, ValueError):
                    continue
            max_age = float(getattr(settings, "standard_max_age_minutes", 180))
            if age_min is not None and age_min > max_age and lifecycle_now(story) in ("CONFIRMED",):
                pubs.mark(pubs.upsert(story_id, platform, payload_hash, int(story["version"])),
                          "SKIPPED", error="STALE_SUPERSEDED")
                log.info("publish suppressed: stale %.0fmin (story %s)", age_min, story_id)
                return True

        # lifecycle-aware rate caps (provisional stories are noisier);
        # INCIDENT-2026-10-04: count NEW posts only — edits add no message.
        lifecycle = story.get("lifecycle") or "CONFIRMED"
        cap = (getattr(settings, "max_provisional_posts_per_hour", 6)
               if lifecycle == "PROVISIONAL"
               else getattr(settings, "max_confirmed_posts_per_hour", 12))
        now = datetime.now(timezone.utc)
        if pubs.new_posts_since(now - timedelta(hours=1)) >= cap:
            return False

        if pubs.already_sent(story_id, platform, payload_hash):
            return True

        # same-message edit policy: a SENT row for this story on this platform
        # IN THE CURRENT PUBLISH CHAT means updates must EDIT that message,
        # never post a duplicate. Rows in a different chat (e.g. misdirected
        # private-chat deliveries) are historical only.
        current_chat = getattr(settings, "telegram_publish_target", "") if platform == "telegram" else ""
        prior = db.query_one(
            "SELECT * FROM publications WHERE story_id=? AND platform=? AND status='SENT' "
            "ORDER BY id DESC LIMIT 1", (story_id, platform))
        if prior and prior.get("remote_id") and (
                not current_chat or not prior.get("chat_id") or prior["chat_id"] == str(current_chat)):
            publisher = telegram_publisher_factory()
            result = await publisher.edit_message(prior["remote_id"], payload.get("text") or "")
            pub_id = pubs.upsert(story_id, platform, payload_hash, int(story["version"]))
            db.execute("UPDATE publications SET chat_id=? WHERE id=?", (str(publisher.chat_id), pub_id))
            if result["ok"]:
                pubs.mark(pub_id, "SENT", remote_id=str(prior["remote_id"]))
                stories.mark_published(story_id)
                return True
            pubs.mark(pub_id, "FAILED", error=result.get("error"))
            return False

        if pubs.new_posts_since(now - timedelta(hours=1)) >= settings.max_posts_per_hour:
            return False
        if pubs.new_posts_since(now - timedelta(hours=24)) >= settings.max_posts_per_day:
            return False
        text = payload.get("text") or ""
        publisher = telegram_publisher_factory()
        result = await publisher.send_message(text)
        pub_id = pubs.upsert(story_id, platform, payload_hash, int(story["version"]))
        db.execute("UPDATE publications SET chat_id=? WHERE id=?", (str(publisher.chat_id), pub_id))
        if result["ok"]:
            pubs.mark(pub_id, "SENT", remote_id=str(result.get("message_id", "")))
            stories.mark_published(story_id)
            return True
        pubs.mark(pub_id, "FAILED", error=result.get("error"))
        return False

    return handler
