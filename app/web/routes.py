"""Public website: server-rendered home/latest/story + trust pages + SEO endpoints."""
from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from app.db.repo import EventsRepo, StoriesRepo
from app.seo.seo import (
    build_graph, build_news_sitemap, build_rss, build_sitemap, robots_txt,
)

templates = Jinja2Templates(directory=os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "templates"))
router = APIRouter()

TRUST_PAGES: dict[str, dict[str, str]] = {
    "about": {"title": "درباره ما"},
    "contact": {"title": "تماس"},
    "editorial-policy": {"title": "سیاست تحریریه"},
    "source-policy": {"title": "سیاست منابع"},
    "verification": {"title": "روش راستی‌آزمایی"},
    "corrections": {"title": "سیاست اصلاحیه‌ها"},
    "ai-use": {"title": "سیاست استفاده از هوش مصنوعی"},
    "privacy": {"title": "حریم خصوصی"},
    "terms": {"title": "شرایط استفاده"},
    "advertising": {"title": "تبلیغات و شفافیت تجاری"},
}


def _draft(story: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(story["draft_json"])
    except Exception:  # noqa: BLE001
        return {}


def _ctx(request: Request, **extra: Any) -> dict[str, Any]:
    brand = request.app.state.brand
    settings = request.app.state.settings
    return {
        "request": request, "brand": brand, "brand_status": brand.brand_status,
        "preview_mode": settings.preview_mode, "base_url": settings.public_base_url,
        **extra,
    }


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    stories = StoriesRepo(request.app.state.db).published(limit=20)
    drafts = {s["id"]: _draft(s) for s in stories}
    return templates.TemplateResponse(request, "public/home.html",
                                      _ctx(request, stories=stories, drafts=drafts))


@router.get("/latest", response_class=HTMLResponse)
async def latest(request: Request):
    stories = StoriesRepo(request.app.state.db).published(limit=100)
    drafts = {s["id"]: _draft(s) for s in stories}
    return templates.TemplateResponse(request, "public/latest.html",
                                      _ctx(request, stories=stories, drafts=drafts))


@router.get("/story/{slug}", response_class=HTMLResponse)
async def story_page(request: Request, slug: str):
    story = StoriesRepo(request.app.state.db).by_slug(slug)
    if not story or story["status"] not in ("PUBLISHED", "CORRECTED"):
        return templates.TemplateResponse(request, "public/404.html", _ctx(request), status_code=404)
    draft = _draft(story)
    settings = request.app.state.settings
    brand = request.app.state.brand
    graph = build_graph(brand, settings.public_base_url or "https://example.invalid", story, draft)
    events = EventsRepo(request.app.state.db)
    related = [s for s in StoriesRepo(request.app.state.db).published(limit=6) if s["id"] != story["id"]][:3]
    return templates.TemplateResponse(request, "public/story.html",
                                      _ctx(request, story=story, draft=draft, graph_json=json.dumps(graph, ensure_ascii=False), related=related))


@router.get("/page/{page}", response_class=HTMLResponse)
async def trust_page(request: Request, page: str):
    meta = TRUST_PAGES.get(page)
    if not meta:
        return templates.TemplateResponse(request, "public/404.html", _ctx(request), status_code=404)
    return templates.TemplateResponse(request, "public/page.html",
                                      _ctx(request, page=page, meta=meta))


@router.get("/robots.txt")
async def robots(request: Request):
    return Response(content=robots_txt(request.app.state.settings.public_base_url),
                    media_type="text/plain")


@router.get("/sitemap.xml")
async def sitemap(request: Request):
    settings = request.app.state.settings
    if settings.preview_mode:
        return Response(content=robots_txt(""), media_type="application/xml", status_code=200)
    stories = StoriesRepo(request.app.state.db).published(limit=500)
    entries = [(s["slug"], s["updated_at"]) for s in stories]
    xml = build_sitemap(settings.public_base_url, entries,
                        ["/latest"] + [f"/page/{p}" for p in TRUST_PAGES])
    return Response(content=xml, media_type="application/xml")


@router.get("/news-sitemap.xml")
async def news_sitemap(request: Request):
    settings = request.app.state.settings
    if settings.preview_mode:
        stories: list[dict[str, Any]] = []
    else:
        stories = StoriesRepo(request.app.state.db).recent(hours=48, limit=200)
    xml = _news_smap(request.app.state, stories)
    return Response(content=xml, media_type="application/xml")


def _news_smap(state, stories):
    brand = state.brand
    base = state.settings.public_base_url.rstrip("/")
    from xml.sax.saxutils import escape

    entries = "".join(
        f"<url><loc>{escape(base)}/story/{escape(s['slug'])}</loc>"
        f"<news:news><news:publication><news:name>{escape(brand.name_fa)}</news:name>"
        f"<news:language>fa</news:language></news:publication>"
        f"<news:publication_date>{escape(s['published_at'] or s['created_at'])}</news:publication_date>"
        f"<news:title>{escape(s['headline'])}</news:title></news:news></url>"
        for s in stories
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
            ' xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">' + entries + "</urlset>")


@router.get("/feed.xml")
async def feed(request: Request):
    state = request.app.state
    if state.settings.preview_mode:
        return Response(content='<?xml version="1.0" encoding="UTF-8"?>'
                                '<rss version="2.0"><channel><title>preview</title></channel></rss>',
                        media_type="application/xml")
    stories = StoriesRepo(state.db).published(limit=50)
    drafts = {s["id"]: _draft(s) for s in stories}
    xml = build_rss(state.brand, state.settings.public_base_url, stories, drafts)
    return Response(content=xml, media_type="application/xml")
