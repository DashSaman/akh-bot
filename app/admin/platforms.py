"""Platforms = where WE PUBLISH (distinct from sources = where we READ)."""
from __future__ import annotations

import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .views import _ctx, _csrf_reject, require_login, templates, _db
from app.db.repo import SettingsRepo

router = APIRouter(prefix="/admin")

_PLATFORMS = ["telegram", "x", "instagram", "threads", "facebook", "website"]


def _platform_state(name: str, request: Request) -> dict:
    s = request.app.state.settings
    repo = SettingsRepo(_db(request))
    env = os.environ
    if name == "telegram":
        configured = bool(s.telegram_bot_token and s.telegram_publish_target)
        status = ("CONNECTED" if configured else "NOT_CONFIGURED")
        if configured and repo.get("telegram_publish_verified_at"):
            status = "LIVE"
        note = "کانال @RastehNews"
    elif name == "x":
        status = "BLOCKED_BY_COST_POLICY"  # current X API publishing = paid tier
        note = "API انتشار رسمی نیازمند اعتبار پولی؛ در ZERO_COST_MODE مسدود"
    elif name in ("instagram", "threads"):
        status = "AUTH_REQUIRED"
        note = "نیازمند OAuth یک‌باره Meta از طرف مالک"
    elif name == "facebook":
        status = "NOT_CONFIGURED"
        note = "آماده اتصال Page API"
    else:
        status = "PREVIEW" if s.preview_mode else "READY"
        note = "پس از تعیین دامن عمومی فعال می‌شود"
    paused = repo.is_paused(name)
    return {"name": name, "status": ("PAUSED" if paused else status),
            "publishing": "OFF" if paused else "ON", "note": note,
            "last_pub": "-", "last_error": "-"}


@router.get("/platforms", response_class=HTMLResponse)
async def platforms_page(request: Request):
    if (r := await require_login(request)):
        return r
    db = _db(request)
    rows = db.query(
        "SELECT platform, MAX(updated_at) lu, MAX(CASE WHEN status='SENT' THEN updated_at END) ls"
        " FROM publications GROUP BY platform")
    last = {r["platform"]: r for r in rows}
    cards = []
    for name in _PLATFORMS:
        c = _platform_state(name, request)
        lr = last.get(name)
        if lr:
            c["last_pub"] = lr["ls"] or lr["lu"]
        cards.append(c)
    return templates.TemplateResponse(request, "admin/platforms.html", _ctx(request, cards=cards))


@router.post("/platforms/{name}/toggle")
async def platform_toggle(request: Request, name: str, csrf: str = Form("")):
    if (r := await require_login(request)) or (c := _csrf_reject(request, csrf)):
        return r or c
    if name in _PLATFORMS:
        repo = SettingsRepo(_db(request))
        key = f"pause_platform:{name}"
        repo.set(key, "0" if repo.get(key) == "1" else "1")
    return RedirectResponse("/admin/platforms", status_code=303)
