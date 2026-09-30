"""Health/readiness. No expensive external calls."""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    db = request.app.state.db
    db.query_one("SELECT 1 AS ok")
    return {"status": "ok", "service": "akh-bot"}


@router.get("/ready")
async def ready(request: Request) -> dict:
    db = request.app.state.db
    db.query_one("SELECT 1 AS ok")
    s = request.app.state.settings
    return {
        "status": "ready",
        "llm": "CONFIGURED" if s.llm_ready else "NOT_CONFIGURED",
        "telegram_publish": "CONFIGURED" if s.telegram_publish_ready else "NOT_CONFIGURED",
        "telegram_ingest": "CONFIGURED" if s.telegram_ingest_ready else "NOT_CONFIGURED",
        "workers": "ON" if s.workers_enabled else "OFF",
        "brand_status": request.app.state.brand.brand_status,
        "preview_mode": s.preview_mode,
    }
