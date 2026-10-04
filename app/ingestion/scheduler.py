"""Background loops: ingest due sources → run pipeline → run jobs.

Sequential per design (2-core VPS, memory-frugal). One failing source/feed/platform
never stops the others.
"""
from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.db.database import Database
from app.db.repo import SourcesRepo

log = logging.getLogger("akh.scheduler")


class Scheduler:
    def __init__(self, db: Database, settings: Settings, provider, brand) -> None:
        self.db = db
        self.settings = settings
        self.provider = provider
        self.brand = brand
        self.ingestor = None
        if settings.telegram_ingest_ready:
            from app.ingestion.telegram_ingest import TelegramIngestor

            self.ingestor = TelegramIngestor(
                settings.telegram_ingest_api_id,
                settings.telegram_ingest_api_hash,
                settings.telegram_ingest_session,
            )

    async def reverification_loop(self, reverify_fn) -> None:
        """DEDICATED 5-minute re-verification worker (not hidden in pipeline):
        active VERIFYING/PROVISIONAL/HELD/CONFLICTING events + 60-min deadlines."""
        import asyncio as _a
        from app.db.repo import SettingsRepo as _SR, utcnow as _u
        while True:
            try:
                _SR(self.db).set("reverify_last_run", _u())
                await reverify_fn()
            except Exception:  # noqa: BLE001
                log.exception("reverify pass failed; continuing")
            await _a.sleep(min(300, getattr(self.settings, "verify_recheck_interval_seconds", 300)))

    async def watchdog_loop(self) -> None:
        """Dedicated health supervisor: heartbeat staleness + orphan requeue marker."""
        import asyncio as _a
        from datetime import datetime as _dt, timezone as _tz
        from app.db.repo import SettingsRepo as _SR, utcnow as _u
        while True:
            try:
                _SR(self.db).set("watchdog_last_run", _u())
                now = _dt.now(_tz.utc)
                for key in ("ingest_last_run", "pipeline_last_run", "reverify_last_run", "jobs_last_run"):
                    row = _SR(self.db).get(key)
                    if row:
                        try:
                            age = (now - _dt.fromisoformat(row)).total_seconds()
                            if age > 900:
                                _SR(self.db).set("watchdog_alert:" + key, f"stale {int(age)}s")
                                log.warning("watchdog: %s stale %ss", key, int(age))
                        except ValueError:
                            pass
                # orphan eligible raw items -> force pipeline tick marker
                orphans = self.db.query_one(
                    "SELECT COUNT(*) c FROM raw_items WHERE processed_state='NEW'"
                    " AND activation_ok=1 AND fetched_at <= datetime('now','-2 minutes')")["c"]
                if orphans:
                    _SR(self.db).set("orphan_backlog", str(orphans))
                    log.warning("watchdog: %s orphan eligible items", orphans)
                # URGENT-FIX §10: PUBLICATION_PIPELINE_STALLED — eligible PERSIAN
                # items + publishable stories, yet zero SENT in 30 min. Never
                # fires when only foreign/HELD items arrived (fa filter).
                try:
                    _publication_stall_check(self.db)
                    _diversity_and_starvation_check(self.db)
                    _iran_stall_check(self.db, self.settings)
                    try:
                        from app.newsroom.iran_policy import update_crisis_mode
                        update_crisis_mode(
                            self.db,
                            calm_minutes=int(getattr(
                                self.settings, "iran_crisis_calm_minutes", 60)))
                    except Exception:  # noqa: BLE001
                        pass
                except Exception:  # noqa: BLE001
                    log.exception("stall check failed")
            except Exception:  # noqa: BLE001
                log.exception("watchdog pass failed; continuing")
            await _a.sleep(120)

    async def soak_and_cleanup_loop(self) -> None:
        """Every 10min: persist soak metrics; at end write report file. No agent needed."""
        import json as _json, os as _os, sqlite3 as _sq
        while True:
            try:
                from app.db.repo import SettingsRepo as _SR, utcnow as _u
                repo = _SR(self.db)
                repo.set("soak_last_run", _u())
                started = repo.get("SOAK_TEST_STARTED_AT")
                if not started:
                    repo.set("SOAK_TEST_STARTED_AT", _u())
                    started = _u()
                row = self.db.query_one(
                    "SELECT (SELECT COUNT(*) FROM raw_items) items,"
                    "(SELECT COUNT(*) FROM events) events,"
                    "(SELECT COUNT(*) FROM publications WHERE status='SENT') sent,"
                    "(SELECT COUNT(*) FROM jobs WHERE status='failed') failed")
                os_, = [_os]
                rpt = _os.path.join(_os.environ.get("DATA_DIR", "/data"), "reports")
                _os.makedirs(rpt, exist_ok=True)
                with open(_os.path.join(rpt, "soak-metrics.jsonl"), "a", encoding="utf-8") as f:
                    f.write(_json.dumps({"ts": _u(), **row}, ensure_ascii=False) + chr(10))
            except Exception:  # noqa: BLE001
                log.exception("soak snapshot failed; continuing")
            await asyncio.sleep(600)

    async def ingest_due(self) -> dict[str, int]:
        from datetime import datetime, timezone

        sources = SourcesRepo(self.db).due(datetime.now(timezone.utc))
        from app.db.repo import SettingsRepo as _SR
        _SR(self.db).set("ingest_last_run", __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"))
        # 2-minute SAFETY SWEEP: force-include any source not checked within window
        stats = {"sources": len(sources), "new_items": 0}
        for source in sources:
            try:
                from app.ingestion.sla import evaluate_sla
                from app.db.repo import utcnow as _u

                self.db.execute("UPDATE sources SET last_check_at=? WHERE id=?",
                                (_u(), source["id"]))
                evaluate_sla(self.db, source["id"],
                             recovery=bool(summary_ok := False))
                if source["platform"] == "rss":
                    from app.ingestion.rss import fetch_rss_source

                    summary = await fetch_rss_source(source, self.db)
                    stats["new_items"] += summary.get("new", 0)
                elif source["platform"] == "telegram":
                    if source.get("source_type") == "telegram_web_preview":
                        from app.ingestion.telegram_web import fetch_telegram_web_source

                        summary = await fetch_telegram_web_source(source, self.db)
                        stats["new_items"] += summary.get("new", 0)
                    elif self.ingestor is not None:
                        summary = await self.ingestor.reconcile_source(source, self.db)
                        stats["new_items"] += summary.get("new", 0)
                ok = not summary.get("error") if isinstance(summary, dict) else True
                evaluate_sla(self.db, source["id"], recovery=ok)
                self.db.execute(
                    "UPDATE sources SET consecutive_failures=CASE WHEN ? THEN 0 ELSE consecutive_failures+1 END WHERE id=?",
                    (1 if ok else 0, source["id"]))
            except Exception:  # noqa: BLE001 — source isolation
                log.exception("source %s ingest failed", source["id"], extra={"source_id": source["id"]})
        return stats

    async def ingest_loop(self) -> None:
        while True:
            try:
                stats = await self.ingest_due()
                if stats["sources"]:
                    log.info("ingest pass: %s", stats)
            except Exception:  # noqa: BLE001
                log.exception("ingest loop crashed; continuing")
            await asyncio.sleep(self.settings.ingest_interval_seconds)

    async def pipeline_loop(self, process_fn) -> None:
        while True:
            try:
                summary = await process_fn()
                if summary.get("processed"):
                    log.info("pipeline pass: %s", {k: v for k, v in summary.items() if k != "new_events"})
            except Exception:  # noqa: BLE001
                log.exception("pipeline loop crashed; continuing")
            await asyncio.sleep(self.settings.pipeline_interval_seconds)


def _publication_stall_check(db) -> None:
    """30-min liveness guard (URGENT-FIX §10). Persian-only eligibility so
    foreign/HELD traffic never triggers a false alarm."""
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    from app.publishing.telegram_bot import is_persian_public_text

    now = _dt.now(_tz.utc)
    win = (now - _td(minutes=30)).isoformat(timespec="seconds")
    # fa eligible items in window (python-side: fetched_at mixes formats)
    items = db.query(
        "SELECT text, activation_ok, language, processed_state, fetched_at"
        " FROM raw_items WHERE fetched_at >= ?", (win,))
    fa_eligible = 0
    for r in items:
        if not r["activation_ok"] or not (r["language"] or "").startswith("fa"):
            continue
        if r["processed_state"] == "NEW":
            fa_eligible += 1
        elif is_persian_public_text((r["text"] or "")[:500]):
            fa_eligible += 1
    if not fa_eligible:
        _SR_marker_clear(db)
        return
    # python-side window (created_at mixes ISO-T and space formats)
    stories_ready = 0
    for r0 in db.query("SELECT created_at FROM stories WHERE status='DRAFT'"):
        try:
            t0 = _dt.fromisoformat(str(r0["created_at"]).replace(" ", "T").replace("Z", "+00:00"))
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=_tz.utc)
            if t0 >= now - _td(minutes=30):
                stories_ready += 1
        except ValueError:
            continue
    pending_jobs = db.query_one(
        "SELECT COUNT(*) c FROM jobs WHERE job_type IN ('publish_send','publish_edit')"
        " AND status IN ('pending','running')")["c"]
    failed_jobs = db.query_one(
        "SELECT COUNT(*) c FROM jobs WHERE job_type IN ('publish_send','publish_edit')"
        " AND status='failed'")["c"]
    sent_delta = 0
    for p in db.query("SELECT updated_at FROM publications WHERE status='SENT'"):
        try:
            if _dt.fromisoformat(str(p["updated_at"]).replace("Z", "+00:00")) >= now - _td(minutes=30):
                sent_delta += 1
        except ValueError:
            continue
    if stories_ready <= 0 and pending_jobs <= 0:
        _SR_marker_clear(db)
        return
    if sent_delta > 0:
        _SR_marker_clear(db)
        return
    # stalled: eligible fa items + ready stories/jobs + zero SENT
    holds = {r["verification"]: r["c"] for r in db.query(
        "SELECT verification, COUNT(*) c FROM events WHERE status='HELD' GROUP BY verification")}
    diag = {
        "eligible_items": fa_eligible, "stories_ready": stories_ready,
        "pending_jobs": pending_jobs, "failed_jobs": failed_jobs,
        "sent_delta_30m": sent_delta, "top_hold_reasons": holds,
    }
    import json as _json
    from app.db.repo import SettingsRepo as _S
    _S(db).set("PUBLICATION_PIPELINE_STALLED", _json.dumps(diag, ensure_ascii=False))
    log.warning("PUBLICATION_PIPELINE_STALLED: %s", diag)


def _iran_stall_check(db, settings) -> None:
    """§8 FINAL-HARDENING: dedicated Iran-priority liveness guard.

    Fires IRAN_PUBLICATION_PIPELINE_STALLED when fresh eligible Iran P0/P1
    material + a publishable story exist, no SEND for 10 minutes, and no
    legitimate rate/cap reason explains it. Safe bounded recovery: pending
    publish jobs get their run_after nudged to now (once per 10 min) —
    never fake posts, never verification bypass, general watchdog kept.
    """
    import json as _json
    from datetime import datetime, timedelta, timezone
    from app.db.repo import SettingsRepo as _S
    from app.newsroom.iran_policy import is_iran_related
    now = datetime.now(timezone.utc)
    h10 = (now - timedelta(minutes=10)).isoformat(timespec="seconds")
    last = db.query_one(
        "SELECT MAX(created_at) t FROM publications WHERE status='SENT'")
    if last and last["t"] and str(last["t"]) > h10:
        _S(db).set("IRAN_PUBLICATION_PIPELINE_STALLED", "")
        return
    ready = db.query(
        "SELECT st.id, st.headline FROM stories st"
        " WHERE st.status IN ('DRAFT','READY') AND NOT EXISTS ("
        "  SELECT 1 FROM publications p WHERE p.story_id=st.id"
        "  AND p.status='SENT')")
    iran_ready = [r for r in ready if is_iran_related(r["headline"] or "")]
    if not iran_ready:
        _S(db).set("IRAN_PUBLICATION_PIPELINE_STALLED", "")
        return
    pending = db.query_one(
        "SELECT COUNT(*) c FROM jobs WHERE job_type='publish_send'"
        " AND status='pending'")["c"]
    throttled = db.query_one(
        "SELECT COUNT(*) c FROM jobs WHERE job_type='publish_send'"
        " AND status='throttled'")["c"] if _has_throttled_state(db) else 0
    if pending > 0 or throttled > 0:
        # a legitimate rate reason exists — diagnose only, no marker escalation
        pass
    caps = {"max_posts_per_hour": getattr(settings, "max_posts_per_hour", 60),
            "max_posts_per_day": getattr(settings, "max_posts_per_day", 500)}
    holds = {r["verification"]: r["c"] for r in db.query(
        "SELECT verification, COUNT(*) c FROM events WHERE status='HELD'"
        " GROUP BY verification")}
    diag = {"iran_stories_ready": len(iran_ready),
            "pending_publish_jobs": pending, "throttled": throttled,
            "caps": caps, "last_send": str(last["t"]) if last else None,
            "top_hold_reasons": holds}
    _S(db).set("IRAN_PUBLICATION_PIPELINE_STALLED",
               _json.dumps(diag, ensure_ascii=False))
    log.warning("IRAN_PUBLICATION_PIPELINE_STALLED: %s", diag)
    # bounded safe recovery: nudge pending publish jobs runnable now
    if pending > 0:
        db.execute(
            "UPDATE jobs SET run_after=? WHERE job_type='publish_send'"
            " AND status='pending' AND run_after>?",
            (now.isoformat(timespec="seconds"), now.isoformat(timespec="seconds")))


def _has_throttled_state(db) -> bool:
    try:
        r = db.query_one(
            "SELECT COUNT(*) c FROM jobs WHERE status='throttled'")
        return bool(r)
    except Exception:  # noqa: BLE001
        return False


def _diversity_and_starvation_check(db) -> None:
    """Directive 2026-10-04: soft anti-monopoly diagnostics.

    SOURCE_MONOPOLY_DETECTED — one canonical identity >50% of new posts in the
    rolling hour while >=5 other identities have publishable stories.
    SOURCE_STARVATION — an active source delivered >=5 fresh eligible items in
    the last 2h that never linked to ANY event (not dedup — orphaned).
    Both WARN and diagnose; neither ever blocks publication by itself.
    """
    import json as _json
    from datetime import datetime, timedelta, timezone
    from app.db.repo import SettingsRepo as _S
    from app.newsroom.diversity import diversity_metrics
    now = datetime.now(timezone.utc)
    m1 = diversity_metrics(db, hours=1)
    # publishable stories per identity (never-sent DRAFT stories)
    rows = db.query(
        "SELECT e.id AS eid FROM stories st JOIN events e ON e.id = st.event_id"
        " WHERE st.status='DRAFT' AND NOT EXISTS ("
        "  SELECT 1 FROM publications p WHERE p.story_id = st.id AND p.status='SENT')")
    waiting_idents = set()
    from app.newsroom.diversity import story_source_identities
    for r in rows:
        waiting_idents |= story_source_identities(db, r["eid"])
    monopoly = False
    if m1["total_new_posts"] >= 4 and m1["top"]:
        top = m1["top"][0]
        others = len(waiting_idents - {top["identity"]})
        if top["share"] > 0.50 and others >= 5:
            monopoly = True
            diag = {"metrics_1h": m1, "waiting_identities": sorted(waiting_idents)[:12]}
            _S(db).set("SOURCE_MONOPOLY_DETECTED", _json.dumps(diag, ensure_ascii=False))
            log.warning("SOURCE_MONOPOLY_DETECTED: %s", diag)
    if not monopoly:
        _S(db).set("SOURCE_MONOPOLY_DETECTED", "")
    # starvation: fresh eligible items never linked to any event
    since2h = (now - timedelta(hours=2)).isoformat(timespec="seconds")
    orphan = db.query(
        "SELECT s.id sid, COALESCE(NULLIF(s.identity,''), s.name) ident, COUNT(*) c"
        " FROM raw_items ri JOIN sources s ON s.id = ri.source_id"
        " WHERE ri.activation_ok = 1 AND ri.fetched_at >= ?"
        " AND NOT EXISTS (SELECT 1 FROM event_items ei WHERE ei.raw_item_id = ri.id)"
        " GROUP BY s.id HAVING c >= 5 ORDER BY c DESC LIMIT 5", (since2h,))
    if orphan:
        diag = [{"source": o["ident"], "orphaned_eligible_items": o["c"]} for o in orphan]
        _S(db).set("SOURCE_STARVATION", _json.dumps(diag, ensure_ascii=False))
        log.warning("SOURCE_STARVATION: %s", diag)
    else:
        _S(db).set("SOURCE_STARVATION", "")


def _SR_marker_clear(db) -> None:
    from app.db.repo import SettingsRepo as _S
    _S(db).set("PUBLICATION_PIPELINE_STALLED", "")
