"""RSS/Atom collector. ETag + If-Modified-Since + gzip via httpx; feedparser for parsing.

Backfill protection: entries published before the source's activated_at are stored
(STORE_ONLY, activation_ok=0) and are never auto-publish eligible.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import feedparser
import httpx

from app.clustering.dedup import fingerprints_for
from app.core.textnorm import detect_language
from app.db.repo import RawItemsRepo, SourcesRepo, parse_iso, utcnow

log = logging.getLogger("akh.ingest.rss")


def _entry_date(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        st = getattr(entry, key, None)
        if st:
            return datetime(*st[:6], tzinfo=timezone.utc)
    return None


def extract_media_refs(entry: Any) -> list[dict[str, str]]:
    """Original-media candidates from ONE feed entry, best first:
    media:content / media:thumbnail → enclosures → first <img>/<video> in
    the summary HTML. Truthful public URLs only — no paywall bypass; entries
    without accessible media simply return an empty list (→ text-only)."""
    import json as _json
    import re as _re

    refs: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(url: str, mtype: str) -> None:
        url = (url or "").strip()
        if not url.startswith(("http://", "https://")) or url in seen:
            return
        seen.add(url)
        refs.append({"url": url, "type": mtype})

    for mc in (getattr(entry, "media_content", None) or []):
        url = mc.get("url", "") if isinstance(mc, dict) else ""
        if url:
            _add(url, "video" if "video" in (mc.get("medium", "") or mc.get("type", "")) else "photo")
    for mt in (getattr(entry, "media_thumbnail", None) or []):
        if isinstance(mt, dict) and mt.get("url"):
            _add(mt["url"], "photo")
    for enc in (getattr(entry, "enclosures", None) or []):
        href = enc.get("href", "") if isinstance(enc, dict) else ""
        etype = enc.get("type", "") or ""
        if href:
            _add(href, "video" if "video" in etype else "photo")
    text = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    if text:
        for m in _re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', text, _re.I)[:2]:
            _add(m, "photo")
        for m in _re.findall(r'<video[^>]+src=["\']([^"\']+)["\']', text, _re.I)[:1]:
            _add(m, "video")
    return refs[:3]


def lineage_for(url: str, forward_from: str | None) -> str:
    if forward_from:
        return f"fwd:{forward_from}"
    try:
        return "dom:" + urlsplit(url).netloc.lower()
    except ValueError:
        return "dom:unknown"


async def fetch_rss_source(source: dict[str, Any], db: Any, *,
                           client: httpx.AsyncClient | None = None,
                           parse_only: bytes | None = None) -> dict[str, Any]:
    """Fetch one approved RSS source; insert new raw items. Returns summary dict."""
    items = RawItemsRepo(db)
    sources = SourcesRepo(db)
    summary: dict[str, Any] = {"source_id": source["id"], "new": 0, "skipped": 0, "not_modified": False}
    activated = parse_iso(source["activated_at"])

    state: dict[str, Any] = {}
    try:
        state = dict(__import__("json").loads(source["fetch_state"] or "{}"))
    except Exception:  # noqa: BLE001
        state = {}

    try:
        if parse_only is not None:
            content, etag, modified, status = parse_only, state.get("etag"), state.get("modified"), 200
        else:
            headers = {"Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"}
            if state.get("etag"):
                headers["If-None-Match"] = state["etag"]
            if state.get("modified"):
                headers["If-Modified-Since"] = state["modified"]
            own_client = client is None
            client = client or httpx.AsyncClient(timeout=25, follow_redirects=True)
            try:
                resp = await client.get(source["url"], headers=headers)
            finally:
                if own_client:
                    await client.aclose()
            status = resp.status_code
            if status == 304:
                summary["not_modified"] = True
                sources.mark_fetch(source["id"], True, fetch_state=state)
                return summary
            if status != 200:
                sources.mark_fetch(source["id"], False, f"HTTP {status}")
                return summary
            content = resp.content
            etag = resp.headers.get("etag")
            modified = resp.headers.get("last-modified")

        parsed = feedparser.parse(content)
        if parsed.bozo and not parsed.entries:
            sources.mark_fetch(source["id"], False, f"invalid XML: {parsed.bozo_exception}"[:300])
            summary["error"] = "invalid XML"
            return summary

        new_state = dict(state)
        if etag:
            new_state["etag"] = etag
        if modified:
            new_state["modified"] = modified

        for entry in parsed.entries[:60]:
            url = getattr(entry, "link", "") or ""
            external_key = url or (getattr(entry, "id", "") or getattr(entry, "title", ""))
            if not external_key or items.exists(source["id"], external_key):
                summary["skipped"] += 1
                continue
            title = getattr(entry, "title", "") or ""
            text = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
            published = _entry_date(entry)
            activation_ok = bool(
                activated is None
                or (published is not None and published >= activated)
            )
            fp = fingerprints_for(url, title, text)
            import json as _json
            media_refs = extract_media_refs(entry)
            item_id = items.insert(
                source_id=source["id"], platform="rss", external_key=external_key,
                url=url, canonical_url=fp["canonical_url"], title=title, text=text,
                language=detect_language(f"{title} {text}"), author=getattr(entry, "author", "") or "",
                published_at=published.isoformat(timespec="seconds") if published else None,
                lineage_key=lineage_for(url, None), activation_ok=activation_ok,
                fingerprints=fp, media=media_refs,
            )
            summary["new"] += 1
            log.info("rss new item %s (source %s)", item_id, source["id"],
                     extra={"raw_item_id": item_id, "source_id": source["id"]})
        sources.mark_fetch(source["id"], True, fetch_state=new_state)
        return summary
    except httpx.HTTPError as e:
        sources.mark_fetch(source["id"], False, f"transport: {e}"[:300])
        summary["error"] = str(e)
        return summary


def utcnow_alias() -> str:  # small helper used by tests
    return utcnow()
