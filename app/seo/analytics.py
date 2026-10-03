"""PART-10 — GROWTH-001: privacy-respecting analytics + metrics.

NO cookies, NO external trackers, NO personal identifiers: each request
records only (day, path-class, referrer-host, utm tags) — aggregate counters,
never user profiles. Plus publication/source metrics + SEO health checks.
"""
from __future__ import annotations

from app.db.database import Database
from app.db.repo import utcnow

PATH_CLASSES = {
    "/": "home", "/latest": "latest", "/feed.xml": "rss",
    "/sitemap.xml": "sitemap", "/news-sitemap.xml": "news_sitemap",
    "/robots.txt": "robots",
}


def record_view(db: Database, path: str, referrer: str = "",
                utm_source: str = "", utm_medium: str = "",
                utm_campaign: str = "") -> None:
    """Aggregate, cookieless view counter. Story pages get their own rows."""
    day = utcnow()[:10]
    p = path or "/"
    if p.startswith("/story/"):
        key = "story:" + p.split("/")[2][:40]
    else:
        key = PATH_CLASSES.get(p, "page:" + (p.split("/")[1][:20] or "other"))
    ref_host = (referrer.split("/")[2] if referrer.startswith("http") else
                (referrer or "-"))[:60]
    utm = (f"{utm_source or '-'}|{utm_medium or '-'}|{utm_campaign or '-'}")[:80]
    db.execute(
        "INSERT INTO analytics_events(day, path_class, referrer_host, utm,"
        " views, created_at, updated_at) VALUES(?,?,?,?,1,?,?)"
        " ON CONFLICT(day, path_class, referrer_host, utm) DO UPDATE SET"
        " views=views+1, updated_at=excluded.updated_at",
        (day, key, ref_host, utm, utcnow(), utcnow()))


def summary(db: Database, days: int = 14) -> dict:
    since = f"-{days} days"
    views = db.query(
        "SELECT day, SUM(views) AS v FROM analytics_events"
        " WHERE day >= date('now', ?) GROUP BY day ORDER BY day DESC", (since,))
    tops = db.query(
        "SELECT path_class, SUM(views) AS v FROM analytics_events"
        " WHERE day >= date('now', ?) GROUP BY path_class"
        " ORDER BY v DESC LIMIT 15", (since,))
    refs = db.query(
        "SELECT referrer_host, SUM(views) AS v FROM analytics_events"
        " WHERE day >= date('now', ?) AND referrer_host != '-'"
        " GROUP BY referrer_host ORDER BY v DESC LIMIT 15", (since,))
    utms = db.query(
        "SELECT utm, SUM(views) AS v FROM analytics_events"
        " WHERE day >= date('now', ?) AND utm != '-|-|-'"
        " GROUP BY utm ORDER BY v DESC LIMIT 15", (since,))
    return {"daily": [dict(r) for r in views], "top_pages": [dict(r) for r in tops],
            "referrers": [dict(r) for r in refs], "utm": [dict(r) for r in utms]}


def publication_metrics(db: Database) -> dict:
    sent = db.query(
        "SELECT p.platform, COUNT(*) AS c FROM publications p"
        " WHERE p.status='SENT' GROUP BY p.platform")
    by_source = db.query(
        "SELECT s.identity, s.name, COUNT(DISTINCT p.story_id) AS stories"
        " FROM publications p JOIN stories st ON st.id=p.story_id"
        " JOIN events e ON e.id=st.event_id"
        " JOIN event_items ei ON ei.event_id=e.id AND ei.is_duplicate=0"
        " JOIN raw_items r ON r.id=ei.raw_item_id"
        " JOIN sources s ON s.id=r.source_id"
        " GROUP BY s.identity ORDER BY stories DESC LIMIT 20")
    lifecycle = db.query(
        "SELECT lifecycle, COUNT(*) AS c FROM stories WHERE status IN"
        " ('PUBLISHED','CORRECTED') GROUP BY lifecycle")
    return {"by_platform": [dict(r) for r in sent],
            "by_source": [dict(r) for r in by_source],
            "lifecycle": [dict(r) for r in lifecycle]}


def seo_health(db: Database, public_base_url: str) -> list[dict]:
    """Truthful SEO checklist items (executable without external services)."""
    items = []
    stories = db.query(
        "SELECT COUNT(*) AS n FROM stories WHERE status IN ('PUBLISHED','CORRECTED')")["n"]
    items.append({"check": "published stories", "value": stories, "ok": stories > 0})
    items.append({"check": "public_base_url", "value": public_base_url or "PREVIEW",
                  "ok": bool(public_base_url)})
    no_slug = db.query(
        "SELECT COUNT(*) AS n FROM stories WHERE slug='' OR slug IS NULL")["n"]
    items.append({"check": "stories missing slug", "value": no_slug, "ok": no_slug == 0})
    no_lead = db.query(
        "SELECT COUNT(*) AS n FROM stories WHERE lead='' OR lead IS NULL")["n"]
    items.append({"check": "stories missing lead", "value": no_lead, "ok": no_lead == 0})
    unverified_public = db.query(
        "SELECT COUNT(*) AS n FROM stories WHERE lifecycle='PROVISIONAL'"
        " AND status='PUBLISHED'")["n"]
    items.append({"check": "provisional live (attribution required)",
                  "value": unverified_public, "ok": True})
    return items
