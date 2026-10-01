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
