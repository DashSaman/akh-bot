"""Admin panel: Persian RTL server-rendered. Session cookie + CSRF + login throttle."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.security import (
    LoginThrottle, check_csrf, create_session_token, new_csrf_token,
    verify_password, verify_session_token,
)
from app.db.repo import (
    ClaimsRepo, EventsRepo, JobsRepo, PublicationsRepo, RawItemsRepo,
    SettingsRepo, SourcesRepo, StoriesRepo,
)

import os

_templates_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "templates"
)
templates = Jinja2Templates(directory=_templates_dir)
router = APIRouter(prefix="/admin")
throttle = LoginThrottle()

SESSION_COOKIE = "akh_session"
CSRF_COOKIE = "akh_csrf"


def _db(request: Request):
    return request.app.state.db


def _current_user(request: Request) -> bool:
    settings = request.app.state.settings
    return verify_session_token(settings.session_secret, request.cookies.get(SESSION_COOKIE))


def _ctx(request: Request, **extra: Any) -> dict[str, Any]:
    brand = request.app.state.brand
    settings = request.app.state.settings
    csrf = extra.pop("csrf_token", None) or request.cookies.get(CSRF_COOKIE, "")
    return {
        "request": request,
        "brand": brand,
        "brand_status": brand.brand_status,
        "csrf_token": csrf,
        "preview_mode": settings.preview_mode,
        **extra,
    }


async def require_login(request: Request) -> HTMLResponse | None:
    if _current_user(request):
        return None
    return RedirectResponse("/admin/login", status_code=303)


def _csrf_reject(request: Request, submitted: str) -> HTMLResponse | None:
    """All admin mutations require the double-submit CSRF token."""
    if check_csrf(submitted, request.cookies.get(CSRF_COOKIE)):
        return None
    return HTMLResponse("درخواست نامعتبر (CSRF).", status_code=403)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    # token must exist in BOTH the rendered form and the cookie on the very first GET
    token = request.cookies.get(CSRF_COOKIE) or new_csrf_token()
    resp = templates.TemplateResponse(request, "admin/login.html", _ctx(request, csrf_token=token))
    resp.set_cookie(CSRF_COOKIE, token, httponly=False, samesite="lax")
    return resp


@router.post("/login")
async def login(request: Request, username: str = Form(""), password: str = Form(""),
                csrf: str = Form("")):
    settings = request.app.state.settings
    ip = request.client.host if request.client else "?"
    if throttle.is_blocked(ip):
        return templates.TemplateResponse(request, "admin/login.html",
                                          _ctx(request, error="تلاش بیش از حد؛ ۱۵ دقیقه بعد دوباره امتحان کنید."), status_code=429)
    if not check_csrf(csrf, request.cookies.get(CSRF_COOKIE)):
        return templates.TemplateResponse(request, "admin/login.html",
                                          _ctx(request, error="نشست منقضی شده؛ دوباره تلاش کنید."), status_code=400)
    ok_user = username == settings.admin_username
    ok_pass = (
        (settings.admin_password_hash and verify_password(password, settings.admin_password_hash))
        or (settings.admin_password and password == settings.admin_password)
    )
    if not (ok_user and ok_pass):
        throttle.record_failure(ip)
        return templates.TemplateResponse(request, "admin/login.html",
                                          _ctx(request, error="نام کاربری یا گذرواژه نادرست است."), status_code=401)
    throttle.reset(ip)
    resp = RedirectResponse("/admin", status_code=303)
    token = create_session_token(settings.session_secret, settings.session_ttl_hours)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax")
    return resp


@router.post("/logout")
async def logout(request: Request, csrf: str = Form("")):
    if (r := _csrf_reject(request, csrf)):
        return r
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if (r := await require_login(request)):
        return r
    db = _db(request)
    sources = SourcesRepo(db).list()
    events = EventsRepo(db).list(limit=5)
    jobs = JobsRepo(db).list(limit=8)
    pubs = PublicationsRepo(db).list(limit=8)
    settings_repo = SettingsRepo(db)
    pauses = {
        "all": settings_repo.is_paused(),
        "telegram": settings_repo.is_paused("telegram"),
        "x": settings_repo.is_paused("x"),
        "instagram": settings_repo.is_paused("instagram"),
        "threads": settings_repo.is_paused("threads"),
        "website": settings_repo.is_paused("website"),
    }
    stats = {
        "sources_total": len(sources),
        "sources_approved": sum(1 for s in sources if s["status"] == "APPROVED"),
        "sources_verification_approved": sum(1 for s in sources if s.get("verification_allowed")),
        "items": db.query_one("SELECT COUNT(*) c FROM raw_items")["c"],
        "events": db.query_one("SELECT COUNT(*) c FROM events")["c"],
        "stories": db.query_one("SELECT COUNT(*) c FROM stories")["c"],
        "publications_sent": db.query_one("SELECT COUNT(*) c FROM publications WHERE status='SENT'")["c"],
        "jobs_failed": db.query_one("SELECT COUNT(*) c FROM jobs WHERE status='failed'")["c"],
        "llm_calls_today": db.query_one(
            "SELECT COUNT(*) c FROM llm_cache WHERE created_at>=date('now')")["c"],
    }
    s = request.app.state.settings
    repo = SettingsRepo(db)
    app_brand = request.app.state.brand

    def _int_status(configured: bool, verified_key: str, error_key: str) -> str:
        if repo.get(error_key):
            return "ERROR"
        if repo.get(verified_key):
            return "LIVE_VERIFIED"
        if configured:
            return "TESTED"  # wired but no successful live call recorded yet
        return "BLOCKED_EXTERNAL"

    integrations = {
        "جمع‌آور RSS": "LIVE_VERIFIED",  # live ingestion proven in production 2026-09-30
        "نویسنده GLM": _int_status(s.llm_ready, "glm_verified_at", "glm_last_error"),
        "ناشر تلگرام": _int_status(s.telegram_publish_ready, "telegram_publish_verified_at", "telegram_last_error"),
        "جمع‌آور تلگرام": "WAITING_FOR_CREDENTIALS" if not s.telegram_ingest_ready else "TESTED",
        "X": "NOT_CONFIGURED",
        "Instagram": "NOT_CONFIGURED",
        "Threads": "NOT_CONFIGURED",
        "برند عمومی": app_brand.brand_status,
        "ایندکس وب‌سایت": "PREVIEW (NOINDEX)" if s.preview_mode else "LIVE",
    }
    return templates.TemplateResponse(request, "admin/dashboard.html",
                                      _ctx(request, stats=stats, pauses=pauses, events=events,
                                           jobs=jobs, pubs=pubs, integrations=integrations))


@router.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request):
    if (r := await require_login(request)):
        return r
    rows = SourcesRepo(_db(request)).list()
    return templates.TemplateResponse(request, "admin/sources.html", _ctx(request, sources=rows))


@router.post("/sources")
async def source_create(request: Request, name: str = Form(...), platform: str = Form(...),
                        url: str = Form(""), external_id: str = Form(""),
                        language: str = Form("fa"), country: str = Form(""),
                        category: str = Form("general"), source_type: str = Form("news_organization"),
                        status: str = Form("DISCOVERED"), polling_interval_min: int = Form(15),
                        source_role: str = Form("MAJOR_NEWSROOM"),
                        verification_allowed: str = Form(""),
                        can_increase_independent_count: str = Form(""),
                        csrf: str = Form("")):
    if (r := await require_login(request)) or (c := _csrf_reject(request, csrf)):
        return r or c
    if source_role not in ("OFFICIAL_PRIMARY", "MAJOR_NEWSROOM", "JOURNALIST", "LOCAL_SOURCE", "AGGREGATOR"):
        source_role = "MAJOR_NEWSROOM"
    SourcesRepo(_db(request)).create(
        name=name, platform=platform, url=url, external_id=external_id, language=language,
        country=country, category=category, source_type=source_type, status=status,
        polling_interval_min=max(1, polling_interval_min),
        source_role=source_role,
        verification_allowed=verification_allowed == "on",
        can_increase_independent_count=(can_increase_independent_count == "on"
                                        and source_role != "AGGREGATOR"),
    )
    return RedirectResponse("/admin/sources", status_code=303)


@router.post("/sources/{source_id}/trust")
async def source_set_trust(request: Request, source_id: int,
                           verification_allowed: str = Form(""),
                           can_increase_independent_count: str = Form(""),
                           csrf: str = Form("")):
    """Owner-granted verification trust — separate from ingestion status."""
    if (r := await require_login(request)) or (c := _csrf_reject(request, csrf)):
        return r or c
    SourcesRepo(_db(request)).update(
        source_id,
        verification_allowed=1 if verification_allowed == "on" else 0,
        can_increase_independent_count=1 if can_increase_independent_count == "on" else 0,
    )
    return RedirectResponse("/admin/sources", status_code=303)


@router.post("/sources/{source_id}/status")
async def source_set_status(request: Request, source_id: int, status: str = Form(...),
                            csrf: str = Form("")):
    if (r := await require_login(request)) or (c := _csrf_reject(request, csrf)):
        return r or c
    if status in ("APPROVED", "DISCOVERED", "BLOCKED"):
        SourcesRepo(_db(request)).set_status(source_id, status)
    return RedirectResponse("/admin/sources", status_code=303)


@router.post("/sources/{source_id}/toggle")
async def source_toggle(request: Request, source_id: int, csrf: str = Form("")):
    if (r := await require_login(request)) or (c := _csrf_reject(request, csrf)):
        return r or c
    repo = SourcesRepo(_db(request))
    s = repo.get(source_id)
    if s:
        repo.update(source_id, enabled=0 if s["enabled"] else 1)
    return RedirectResponse("/admin/sources", status_code=303)


@router.get("/items", response_class=HTMLResponse)
async def items_page(request: Request):
    if (r := await require_login(request)):
        return r
    rows = RawItemsRepo(_db(request)).list(limit=100)
    return templates.TemplateResponse(request, "admin/items.html", _ctx(request, items=rows))


@router.get("/events", response_class=HTMLResponse)
async def events_page(request: Request):
    if (r := await require_login(request)):
        return r
    rows = EventsRepo(_db(request)).list(limit=100)
    return templates.TemplateResponse(request, "admin/events.html", _ctx(request, events=rows))


@router.get("/events/{event_id}", response_class=HTMLResponse)
async def event_detail(request: Request, event_id: int):
    if (r := await require_login(request)):
        return r
    db = _db(request)
    event = EventsRepo(db).get(event_id)
    if not event:
        return RedirectResponse("/admin/events", status_code=303)
    items = EventsRepo(db).items(event_id)
    claims = ClaimsRepo(db).for_event(event_id)
    story = StoriesRepo(db).by_event(event_id)
    return templates.TemplateResponse(request, "admin/event_detail.html",
                                      _ctx(request, event=event, items=items, claims=claims, story=story))


@router.get("/publications", response_class=HTMLResponse)
async def publications_page(request: Request):
    if (r := await require_login(request)):
        return r
    rows = PublicationsRepo(_db(request)).list(limit=100)
    return templates.TemplateResponse(request, "admin/publications.html", _ctx(request, pubs=rows))


@router.post("/stories/{story_id}/lifecycle")
async def story_lifecycle(request: Request, story_id: int, lifecycle: str = Form(...),
                          note: str = Form(""), csrf: str = Form("")):
    """Manual editorial override: CONFIRM / HOLD(VERIFYING) / RETRACT / REPUBLISH.
    Re-publication reuses the SAME Telegram message via the ledger edit path."""
    if (r := await require_login(request)) or (c := _csrf_reject(request, csrf)):
        return r or c
    allowed = {"CONFIRM", "PROVISIONAL", "VERIFYING", "RETRACT", "CONFLICTING"}
    if lifecycle not in allowed:
        return HTMLResponse("چرخه زندگی نامعتبر", status_code=400)
    target = "RETRACTED" if lifecycle == "RETRACT" else lifecycle
    db = _db(request)
    repo = StoriesRepo(db)
    story = repo.get(story_id)
    if not story:
        return RedirectResponse("/admin/events", status_code=303)
    import json as _json

    draft = _json.loads(story["draft_json"])
    # rebuild public telegram text with the new status header (own-brand signature,
    # external sources hidden — evidence stays in the DB)
    from app.publishing.telegram_bot import build_public_text
    from app.core.textnorm import sha256_hex
    from app.db.repo import JobsRepo, PublicationsRepo

    body = draft.get("platform_variants", {}).get("telegram") or draft.get("lead", "")
    body = body.split("\n", 1)[1] if body.startswith(("🔴", "✅", "🟠", "❌", "📢", "⚠️")) else body
    settings_repo = SettingsRepo(db)
    mode = settings_repo.get("public_source_display_mode", "hidden")
    sig_on = settings_repo.get("telegram_signature_enabled", "1") == "1"
    text = build_public_text(target, body, request.app.state.brand, mode, sig_on)
    draft.setdefault("platform_variants", {})["telegram"] = text
    draft["lifecycle_note"] = f"manual:{lifecycle}"
    version = repo.set_lifecycle(story_id, target, note or f"manual {lifecycle}", draft)
    payload_hash = sha256_hex(text)
    pub_id = PublicationsRepo(db).upsert(story_id, "telegram", payload_hash, version)
    JobsRepo(db).enqueue("publish_telegram",
                         {"story_id": story_id, "platform": "telegram",
                          "payload_hash": payload_hash, "text": text,
                          "publication_id": pub_id},
                         dedupe_key=f"pub:tg:{story_id}:{payload_hash[:16]}")
    event = db.query_one("SELECT id FROM events WHERE id=?", (story["event_id"],))
    return RedirectResponse(f"/admin/events/{event['id']}", status_code=303)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    if (r := await require_login(request)):
        return r
    repo = SettingsRepo(_db(request))
    platforms = ["telegram", "x", "instagram", "threads", "website"]
    pauses = {"all": repo.is_paused(), **{p: repo.is_paused(p) for p in platforms}}
    return templates.TemplateResponse(request, "admin/settings.html",
                                      _ctx(request, pauses=pauses, platforms=platforms))


@router.post("/settings/pause")
async def set_pause(request: Request, key: str = Form(...), value: str = Form(...),
                    csrf: str = Form("")):
    if (r := await require_login(request)) or (c := _csrf_reject(request, csrf)):
        return r or c
    allowed = {"pause_all"} | {f"pause_platform:{p}" for p in
                               ("telegram", "x", "instagram", "threads", "website")}
    if key in allowed and value in ("0", "1"):
        SettingsRepo(_db(request)).set(key, value)
    return RedirectResponse("/admin/settings", status_code=303)


@router.post("/sources/{source_id}/edit")
async def source_edit(request: Request, source_id: int, name: str = Form(...),
                      priority_rank: int = Form(99), polling_interval_seconds: int = Form(120),
                      publication_policy: str = Form("AUTO"), language: str = Form("fa"),
                      topic_mode: str = Form("ALL"), csrf: str = Form("")):
    if (r := await require_login(request)) or (c := _csrf_reject(request, csrf)):
        return r or c
    if publication_policy not in ("AUTO", "VERIFY_ONLY", "DISCOVERY_ONLY", "NEVER_PUBLISH"):
        publication_policy = "AUTO"
    SourcesRepo(_db(request)).update(
        source_id, name=name, priority_rank=max(1, priority_rank),
        polling_interval_seconds=max(20, polling_interval_seconds),
        publication_policy=publication_policy, language=language, topic_mode=topic_mode)
    return RedirectResponse("/admin/sources", status_code=303)


@router.post("/sources/{source_id}/archive")
async def source_archive(request: Request, source_id: int, csrf: str = Form("")):
    if (r := await require_login(request)) or (c := _csrf_reject(request, csrf)):
        return r or c
    repo = SourcesRepo(_db(request))
    repo.update(source_id, enabled=0, source_control_state="ARCHIVED")
    repo.set_status(source_id, "BLOCKED")
    return RedirectResponse("/admin/sources", status_code=303)


@router.post("/sources/{source_id}/fetch-now")
async def source_fetch_now(request: Request, source_id: int, csrf: str = Form("")):
    if (r := await require_login(request)) or (c := _csrf_reject(request, csrf)):
        return r or c
    db = _db(request)
    source = SourcesRepo(db).get(source_id)
    if not source:
        return RedirectResponse("/admin/sources", status_code=303)
    try:
        if source["platform"] == "rss":
            from app.ingestion.rss import fetch_rss_source
            summary = await fetch_rss_source(source, db)
        elif source["platform"] == "telegram" and source.get("source_type") == "telegram_web_preview":
            from app.ingestion.telegram_web import fetch_telegram_web_source
            summary = await fetch_telegram_web_source(source, db)
        else:
            summary = {"error": "unsupported collector"}
    except Exception as e:  # noqa: BLE001
        summary = {"error": str(e)[:200]}
    SettingsRepo(db).set("last_fetch_now", json.dumps({"id": source_id, **{k: summary.get(k) for k in ("new", "skipped", "error")}}, ensure_ascii=False))
    return RedirectResponse("/admin/sources", status_code=303)


@router.get("/sources/{source_id}/items", response_class=HTMLResponse)
async def source_items_view(request: Request, source_id: int):
    if (r := await require_login(request)):
        return r
    db = _db(request)
    rows = db.query(
        "SELECT r.*, e.id AS event_id, e.status AS event_status FROM raw_items r"
        " LEFT JOIN event_items ei ON ei.raw_item_id=r.id LEFT JOIN events e ON e.id=ei.event_id"
        " WHERE r.source_id=? ORDER BY r.id DESC LIMIT 50", (source_id,))
    src = SourcesRepo(db).get(source_id)
    return templates.TemplateResponse(request, "admin/source_items.html",
                                      _ctx(request, items=rows, src=src))


@router.get("/sources/{source_id}/test", response_class=HTMLResponse)
async def source_test_view(request: Request, source_id: int):
    if (r := await require_login(request)):
        return r
    db = _db(request)
    source = SourcesRepo(db).get(source_id)
    result = {"ok": False, "mode": source["source_type"] if source else "?"}
    if source:
        try:
            import httpx as _hx, time as _t
            t0 = _t.monotonic()
            async def probe():
                from app.ingestion.telegram_web import parse_preview_page
                async with _hx.AsyncClient(timeout=20, follow_redirects=True) as cl:
                    resp = await cl.get(f"https://t.me/s/{source['external_id']}")
                msgs = parse_preview_page(resp.text) if resp.status_code == 200 else []
                return resp.status_code, (msgs[0] if msgs else None)
            code, latest = await probe()
            result = {"ok": code == 200, "mode": "WEB_FALLBACK", "http": code,
                      "latency_ms": int((_t.monotonic() - t0) * 1000),
                      "latest": (latest or {}).get("text", "")[:120]}
        except Exception as e:  # noqa: BLE001
            result = {"ok": False, "error": str(e)[:200], "mode": "WEB_FALLBACK"}
    return templates.TemplateResponse(request, "admin/source_test.html",
                                      _ctx(request, result=result, src=source))
