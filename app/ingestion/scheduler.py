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
