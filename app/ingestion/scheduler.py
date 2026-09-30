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

    async def ingest_due(self) -> dict[str, int]:
        from datetime import datetime, timezone

        sources = SourcesRepo(self.db).due(datetime.now(timezone.utc))
        stats = {"sources": len(sources), "new_items": 0}
        for source in sources:
            try:
                if source["platform"] == "rss":
                    from app.ingestion.rss import fetch_rss_source

                    summary = await fetch_rss_source(source, self.db)
                    stats["new_items"] += summary.get("new", 0)
                elif source["platform"] == "telegram":
                    if self.ingestor is None:
                        continue
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
