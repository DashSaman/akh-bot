"""akh-bot application entrypoint.

Lightweight modular monolith: FastAPI + SQLite WAL + asyncio loops.
Internal namespace: akhbot. Public brand: configurable, currently UNDECIDED.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.brand import load_brand
from app.config import Settings, get_settings
from app.core.logs import setup_logging
from app.db.database import Database
from app.db.migrate import apply_migrations

log = logging.getLogger("akh.main")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    brand = load_brand(settings.brand_config)
    db = Database(settings.db_path)
    apply_migrations(db)

    from app.integrations.llm.base import LLMProvider
    from app.integrations.llm.glm import GlmProvider
    from app.db.repo import LlmCacheRepo

    provider: LLMProvider | None = None
    if settings.llm_ready:
        provider = GlmProvider(
            settings.glm_api_key, settings.glm_base_url, settings.glm_model,
            cache=LlmCacheRepo(db), timeout=settings.llm_timeout_seconds,
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks = []
        if settings.workers_enabled:
            import asyncio

            from app.jobs.runner import JobRunner, make_publish_handler
            from app.newsroom.pipeline import process_new_items
            from app.ingestion.scheduler import Scheduler
            from app.publishing.telegram_bot import TelegramBotPublisher

            scheduler = Scheduler(db, settings, provider, brand)
            runner = JobRunner(db, settings)
            runner.register(
                "publish_telegram",
                make_publish_handler(
                    db, settings,
                    lambda: TelegramBotPublisher(
                        settings.telegram_bot_token,
                        settings.telegram_publish_target,  # validated channel ONLY — no fallback
                    ),
                ),
            )
            loop = asyncio.get_running_loop()
            tasks = [
                loop.create_task(scheduler.ingest_loop(), name="ingest"),
                loop.create_task(scheduler.pipeline_loop(
                    lambda: process_new_items(db, provider, brand, settings)), name="pipeline"),
                loop.create_task(runner.loop(), name="jobs"),
                loop.create_task(scheduler.soak_and_cleanup_loop(), name="soak"),
                loop.create_task(scheduler.reverification_loop(
                    lambda: process_new_items(db, provider, brand, settings)), name="reverify"),
                loop.create_task(scheduler.watchdog_loop(), name="watchdog"),
            ]
            log.info("workers started (ingest/pipeline/jobs)")
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            db.close()

    app = FastAPI(title="akh-bot", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.brand = brand
    app.state.db = db
    app.state.provider = provider

    app.mount("/static", StaticFiles(directory=_pkg_path("static")), name="static")

    from app.api.routes import router as api_router

    app.include_router(api_router)
    from app.admin.views import router as admin_router

    app.include_router(admin_router)
    from app.web.routes import router as web_router

    app.include_router(web_router)
    return app


def _pkg_path(sub: str) -> str:
    import os

    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), sub)


app = create_app()
