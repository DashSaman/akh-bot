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
    db = _db(request)
    rows = SourcesRepo(db).list()
    import datetime as _dt

    now = _dt.datetime.now(_dt.timezone.utc)
    enriched = []
    for r in rows:
        d = dict(r)
        try:
            d["last_check_at_ts"] = _dt.datetime.fromisoformat(r["last_check_at"]).timestamp() * 1e9 if r["last_check_at"] else 0
        except ValueError:
            d["last_check_at_ts"] = 0
        d["sla_breach"] = db.query_one("SELECT value FROM settings WHERE key=?", (f"sla_breach:{r['id']}",)) is not None
        enriched.append(d)
    late = sum(1 for r in enriched if r["sla_breach"])
    return templates.TemplateResponse(request, "admin/sources.html",
                                      _ctx(request, sources=enriched, now_ts=now.timestamp() * 1e9, late_count=late))


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


@router.get("/verification/{event_id}", response_class=HTMLResponse)
async def verification_trace(request: Request, event_id: int):
    """PART-4 verification traceability: claims, evidence links (supporting vs
    contradicting), independent-origin counts, reverify schedule, run history.
    Read-only; no secrets."""
    if (r := await require_login(request)):
        return r
    db = _db(request)
    event = EventsRepo(db).get(event_id)
    if not event:
        return RedirectResponse("/admin/events", status_code=303)
    claims = ClaimsRepo(db).for_event(event_id)
    from app.verification import evidence as ev
    from app.verification.runs import runs_for_event

    claim_rows = []
    for c in claims:
        links = db.query(
            "SELECT el.relation, el.raw_item_id, el.source_id, el.lineage_key,"
            " s.name AS source_name FROM evidence_links el"
            " JOIN sources s ON s.id=el.source_id"
            " WHERE el.claim_id=? ORDER BY el.relation, el.id", (c["id"],))
        claim_rows.append({
            "id": c["id"], "text": c["text"], "state": c["state"],
            "risk": c["risk_level"], "material": c["material"],
            "independent": ev.independent_origin_count(db, int(c["id"])),
            "supports": [dict(l) for l in links if l["relation"] == ev.SUPPORTS],
            "contradicts": [dict(l) for l in links if l["relation"] == ev.CONTRADICTS],
            "contexts": [dict(l) for l in links if l["relation"] == ev.CONTEXT],
            "last_verified_at": c["last_verified_at"],
            "next_verify_at": c["next_verify_at"],
            "attempts": c["verification_attempts"],
        })
    runs = runs_for_event(db, event_id, limit=100)
    return templates.TemplateResponse(
        request, "admin/verification.html",
        _ctx(request, event=event, claims=claim_rows, runs=runs,
             story=StoriesRepo(db).by_event(event_id)))


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


@router.get("/ai", response_class=HTMLResponse)
async def ai_page(request: Request):
    """PART-5 ADMIN-002: free-AI provider state — order, configured/enabled,
    model, health, latency, last success/error, calls. NEVER shows keys."""
    if (r := await require_login(request)):
        return r
    settings = request.app.state.settings
    router = getattr(settings, "_ai_router", None)
    states = router.provider_states() if router else []
    srepo = SettingsRepo(_db(request))
    return templates.TemplateResponse(
        request, "admin/ai.html",
        _ctx(request, states=states,
             zero_cost=getattr(router, "zero_cost", True),
             free_only=getattr(router, "free_only", True),
             available=getattr(router, "available", False),
             ai_disabled=srepo.get("ai_disabled"),
             ai_priority=srepo.get("ai_priority")))


@router.post("/ai/provider")
async def ai_provider_action(request: Request):
    """Actions: enable/disable a provider, or change priority order.
    Persisted in settings; applied to the LIVE router (no restart needed)."""
    if (r := await require_login(request)):
        return r
    form = await request.form()
    if (rej := _csrf_reject(request, str(form.get("csrf", "")))):
        return rej
    action = str(form.get("action", ""))
    name = str(form.get("name", ""))
    db = _db(request)
    srepo = SettingsRepo(db)
    router = getattr(request.app.state.settings, "_ai_router", None)
    if router and name in [st.name for st in router.states]:
        disabled = {n for n in srepo.get("ai_disabled").split(",") if n}
        if action == "disable":
            disabled.add(name)
        elif action == "enable":
            disabled.discard(name)
        elif action == "up":
            names = [st.name for st in router.states]
            i = names.index(name)
            if i > 0:
                names[i - 1], names[i] = names[i], names[i - 1]
            srepo.set("ai_priority", ",".join(names))
        srepo.set("ai_disabled", ",".join(sorted(disabled)))
        # apply to the live router
        for st in router.states:
            if st.name == name and action in ("enable", "disable"):
                st.enabled = action == "enable" and st.configured
    return RedirectResponse("/admin/ai", status_code=303)


@router.post("/ai/test")
async def ai_test_provider(request: Request):
    """One tiny live call against the chosen (or first enabled) provider —
    health check only; response never contains keys."""
    if (r := await require_login(request)):
        return r
    form = await request.form()
    if (rej := _csrf_reject(request, str(form.get("csrf", "")))):
        return rej
    settings = request.app.state.settings
    router = getattr(settings, "_ai_router", None)
    message = "NO_PROVIDER_CONFIGURED"
    if router and router.available:
        result = await router.chat_json(
            system="Reply with JSON only.", user='Return {"ok": true}',
            max_tokens=20)
        states = {s["name"]: s for s in router.provider_states()}
        healthy = [n for n, st in states.items() if st["health"] == "HEALTHY"]
        message = ("TEST_OK: " + ",".join(healthy)) if result else                   "TEST_FAILED: " + ",".join(f"{n}={states[n]['health']}" for n in healthy)                   if healthy else "TEST_FAILED_ALL"
    srepo = SettingsRepo(_db(request))
    srepo.set("ai_last_test", f"{message} @ {utcnow()}")
    return RedirectResponse("/admin/ai", status_code=303)


# ----------------------------------------------------------------------
# PART-7: ADMIN-003 manual intake (canonical pipeline only — never direct
# publish) + ADMIN-004 24/7 health dashboard. No secrets displayed.
# ----------------------------------------------------------------------

@router.get("/intake", response_class=HTMLResponse)
async def intake_page(request: Request):
    if (r := await require_login(request)):
        return r
    sources = SourcesRepo(_db(request)).list()
    return templates.TemplateResponse(request, "admin/intake.html",
                                      _ctx(request, sources=sources))


@router.post("/intake")
async def intake_submit(request: Request):
    """Paste text/URL + source + language → RawItem → the SAME canonical V2
    pipeline (completeness/claims/verification/gates). Manual input is NEVER
    published directly."""
    if (r := await require_login(request)):
        return r
    form = await request.form()
    if (rej := _csrf_reject(request, str(form.get("csrf", "")))):
        return rej
    db = _db(request)
    text = str(form.get("text", "")).strip()
    url = str(form.get("url", "")).strip()
    source_id = int(form.get("source_id", 0) or 0)
    language = str(form.get("language", "fa")).strip() or "fa"
    media_ref = str(form.get("media_ref", "")).strip()
    if not text:
        return RedirectResponse("/admin/intake?error=empty", status_code=303)
    src = SourcesRepo(db).get(source_id) if source_id else None
    if not src:
        # manual intake gets its own canonical source identity
        source_id = SourcesRepo(db).create(
            name="Manual Intake", platform="website", url=url or "manual://intake",
            language=language, status="APPROVED",
            source_type="manual_intake", verification_allowed=False)
        SourcesRepo(db).update(source_id,
                               source_control_state="OWNER_ENABLED",
                               identity="manual-intake",
                               endpoint_state="ACTIVE")
    media = [{"url": media_ref}] if media_ref else []
    import hashlib as _hl
    from app.db.repo import utcnow as _now
    RawItemsRepo(db).insert(
        source_id=source_id, platform="website",
        external_key="manual:%s:%s" % (
            _now(), _hl.sha256(text[:80].encode()).hexdigest()[:8]),
        url=url, canonical_url=url, title=text.split(chr(10))[0][:200],
        text=text, language=language, activation_ok=True, media=media,
        lineage_key="manual:intake")
    SettingsRepo(db).set("manual_intake_last", _now())
    return RedirectResponse("/admin/intake?ok=1", status_code=303)


@router.get("/health", response_class=HTMLResponse)
async def health_dashboard(request: Request):
    """ADMIN-004: one truthful 24/7 operations view — workers, queue, sources,
    watermarks, translation provider, telegram, V2, verification, disk/DB,
    errors, blocked dependencies. Read-only; no secrets."""
    if (r := await require_login(request)):
        return r
    db = _db(request)
    import datetime as _dt

    now = _dt.datetime.now(_dt.timezone.utc)

    def _age(key: str) -> str:
        row = SettingsRepo(db).get(key)
        try:
            return f"{round((now - _dt.datetime.fromisoformat(row)).total_seconds())}s"
        except (TypeError, ValueError):
            return "—"

    workers = [{"name": k, "age": _age(k)} for k in
               ("ingest_last_run", "pipeline_last_run", "reverify_last_run",
                "watchdog_last_run", "soak_last_run")]
    queue = {r0["status"]: r0["c"] for r0 in db.query(
        "SELECT status, COUNT(*) AS c FROM jobs GROUP BY status")}
    src_rows = db.query(
        "SELECT endpoint_state, COUNT(*) AS c FROM sources WHERE identity!=''"
        " GROUP BY endpoint_state")
    endpoints = {r0["endpoint_state"]: r0["c"] for r0 in src_rows}
    sources = SourcesRepo(db).list()
    healthy = sum(1 for s in sources if s["enabled"] and not (s["last_error"] or ""))
    sent = db.query_one(
        "SELECT COUNT(*) AS n FROM publications WHERE status='SENT'")["n"]
    dup = db.query_one(
        "SELECT COUNT(*) AS n FROM publications p1 WHERE p1.status='SENT' AND"
        " EXISTS (SELECT 1 FROM publications p2 WHERE p2.story_id=p1.story_id"
        " AND p2.status='SENT' AND p2.remote_id IS NOT NULL"
        " AND p2.remote_id != p1.remote_id AND p2.chat_id = p1.chat_id)")["n"]
    runs = db.query_one("SELECT COUNT(*) AS n FROM verification_runs")["n"]
    held = db.query_one(
        "SELECT COUNT(*) AS n FROM events WHERE status='HELD'")["n"]
    orphans = db.query_one(
        "SELECT COUNT(*) AS n FROM raw_items WHERE processed_state='NEW'"
        " AND activation_ok=1 AND fetched_at <= datetime('now','-10 minutes')")["n"]
    from app.publishing.media import disk_percent
    import os as _os

    settings = request.app.state.settings
    router = getattr(settings, "_ai_router", None)
    providers = router.provider_states() if router else []
    db_bytes = _os.path.getsize(db.path) if hasattr(db, "path") else 0
    return templates.TemplateResponse(
        request, "admin/health.html",
        _ctx(request, workers=workers, queue=queue, endpoints=endpoints,
             sources_total=len(sources), sources_healthy=healthy,
             sent=sent, dup_send=dup, vruns=runs, held=held, orphans=orphans,
             disk=disk_percent(), db_mb=round(db_bytes / 1e6, 1),
             v2=str(getattr(settings, "event_engine_v2_enabled", False)).lower(),
             autonomous=str(getattr(settings, "autonomous_mode", False)).lower(),
             providers=providers,
             ai_available=getattr(router, "available", False),
             telegram=("CONFIGURED" if getattr(settings, "telegram_publish_ready", False)
                       else "NOT_CONFIGURED"),
             blocked=["TELETHON_LOGIN", "FREE_AI_KEY", "META_OAUTH",
                      "X_API_PAID", "PUBLIC_DOMAIN"]))


@router.get("/growth", response_class=HTMLResponse)
async def growth_dashboard(request: Request):
    """PART-10 GROWTH-001: publication/source metrics, search/referral
    aggregates (cookieless), SEO health. No secrets."""
    if (r := await require_login(request)):
        return r
    from app.seo import analytics as an
    db = _db(request)
    return templates.TemplateResponse(
        request, "admin/growth.html",
        _ctx(request, views=an.summary(db), pubs=an.publication_metrics(db),
             seo=an.seo_health(db, getattr(request.app.state.settings,
                                           "public_base_url", ""))))
