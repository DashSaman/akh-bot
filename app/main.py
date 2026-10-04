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

    from app.integrations.llm.router import FreeAiRouter

    # PART-5: provider enable/disable + priority persist in settings (DB);
    # construction resolves everything once from the environment snapshot.
    from app.db.repo import SettingsRepo as _SR

    _ai_state = _SR(db)
    _disabled = {n.split(":", 1)[1] for n in (_ai_state.get("ai_disabled") or "").split(",") if n}
    _order = [n for n in (_ai_state.get("ai_priority") or "").split(",") if n] or None
    settings._ai_router = FreeAiRouter(disabled=_disabled, priority_order=_order)
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

            from app.jobs.runner import (
                JobRunner, make_edit_handler, make_publish_handler, make_send_handler,
            )
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
            # P3-E: distinct job types — publish_send NEVER fires when a SENT
            # publication exists; publish_edit NEVER sends (edits same message).
            runner.register("publish_send", make_send_handler(
                db, settings,
                lambda: TelegramBotPublisher(
                    settings.telegram_bot_token, settings.telegram_publish_target),
            ))
            runner.register("publish_edit", make_edit_handler(
                db, settings,
                lambda: TelegramBotPublisher(
                    settings.telegram_bot_token, settings.telegram_publish_target),
            ))
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
                loop.create_task(_telethon_task(db, settings), name="telethon"),
            ]
            # E1: editorial intake poller — feature-flagged, OFF by default;
            # bootstrap_owner seeds the OWNER row from safe config (E3).
            if getattr(settings, "editorial_bot_intake_enabled", False):
                from app.editorial.intake import EditorialIntake, bootstrap_owner
                try:
                    bootstrap_owner(db, settings)
                    tasks.append(loop.create_task(
                        EditorialIntake(db, settings).loop(), name="editorial"))
                    log.info("editorial intake worker started")
                except Exception:  # noqa: BLE001 — never block production
                    log.exception("editorial intake failed to start (ignored)")
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

    @app.middleware("http")
    async def _analytics(request, call_next):
        """GROWTH-001: cookieless aggregate views (public pages only)."""
        resp = await call_next(request)
        try:
            p = request.url.path
            if (request.method == "GET"
                    and not p.startswith(("/admin", "/api", "/static", "/login"))
                    and not p.endswith((".css", ".js", ".ico", ".png", ".jpg", ".xml", ".txt"))):
                from app.seo import analytics as _an
                q = request.query_params
                _an.record_view(
                    app.state.db, p, referrer=request.headers.get("referer", ""),
                    utm_source=q.get("utm_source", ""),
                    utm_medium=q.get("utm_medium", ""),
                    utm_campaign=q.get("utm_campaign", ""))
        except Exception:  # noqa: BLE001
            pass
        return resp

    app.mount("/static", StaticFiles(directory=_pkg_path("static")), name="static")

    from app.api.routes import router as api_router

    app.include_router(api_router)
    from app.admin.views import router as admin_router
    from app.admin.platforms import router as platforms_router
    from app.admin.media_views import router as media_router

    app.include_router(admin_router)
    app.include_router(platforms_router)
    app.include_router(media_router)
    from app.admin.bot_admins import router as bot_admins_router
    from app.admin.editorial_inbox import router as editorial_inbox_router
    app.include_router(bot_admins_router)
    app.include_router(editorial_inbox_router)
    from app.web.routes import router as web_router

    app.include_router(web_router)
    return app


async def _telethon_task(db, settings):
    from app.ingestion.telethon_listener import TelethonListener

    tl = TelethonListener(db, settings)
    try:
        await tl.run()  # no creds → returns immediately; WEB_FALLBACK authoritative
    except Exception:  # noqa: BLE001 — never crash other workers (§20)
        pass


def _pkg_path(sub: str) -> str:
    import os

    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), sub)


app = create_app()
