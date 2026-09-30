"""Telegram PUBLIC-CHANNEL monitoring via the t.me/s/<channel> web preview.

No Telethon session required (public content only). Each channel's HTML preview
page exposes message blocks with stable data-post ids, text and datetime.
Used for WATCH sources; backfill protection applies as everywhere else.
"""
from __future__ import annotations

import html as html_mod
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.clustering.dedup import fingerprints_for
from app.core.textnorm import detect_language
from app.db.repo import RawItemsRepo, SourcesRepo, parse_iso

log = logging.getLogger("akh.ingest.tgweb")

_POST_RE = re.compile(
    r'<div[^>]*class="tgme_widget_message [^"]*"[^>]*data-post="(?P<post>[^"]+)"(.*?)</div>\s*<div[^>]*class="tgme_widget_message_footer',
    re.DOTALL,
)
_TEXT_RE = re.compile(
    r'<div[^>]*class="tgme_widget_message_text[^"]*"[^>]*>(?P<html>.*?)</div>', re.DOTALL
)
_TIME_RE = re.compile(r'<time[^>]*datetime="(?P<dt>[^"]+)"')
_TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def parse_preview_page(body: str) -> list[dict[str, Any]]:
    """Extract messages from a t.me/s/ page (split at each message block)."""
    msgs: list[dict[str, Any]] = []
    segments = re.split(r'(?=<div[^>]*data-post=")', body)
    for seg in segments[1:]:
        pm = re.search(r'data-post="([^"]+)"', seg)
        tm = _TEXT_RE.search(seg)
        if not (pm and tm):
            continue
        text = _TAG_RE.sub("\n", tm.group("html"))
        text = html_mod.unescape(re.sub(r"<[^>]+>", " ", text))
        text = re.sub(r"[ \t]+", " ", text).strip()
        if not text:
            continue
        published = None
        dt = _TIME_RE.search(seg)
        if dt:
            try:
                published = datetime.fromisoformat(dt.group("dt")).astimezone(timezone.utc)
            except ValueError:
                published = None
        msgs.append({"post": pm.group(1), "text": text,
                     "published": published.isoformat(timespec="seconds") if published else None})
    seen, out = set(), []
    for x in msgs:
        if x["post"] not in seen:
            seen.add(x["post"])
            out.append(x)
    return out


async def fetch_telegram_web_source(source: dict[str, Any], db: Any, limit: int = 20) -> dict[str, Any]:
    items = RawItemsRepo(db)
    sources = SourcesRepo(db)
    handle = (source["external_id"] or source["url"].rstrip("/").split("/")[-1]).lstrip("@")
    summary: dict[str, Any] = {"source_id": source["id"], "handle": handle, "new": 0, "skipped": 0}
    try:
        import json as _json
        state = _json.loads(source.get("fetch_state") or "{}")
        watermark = int(state.get("watermark") or 0)
        pages, all_msgs, before = 0, [], None
        async with httpx.AsyncClient(timeout=25, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 (compatible; akhbot/0.1)"}) as client:
            while pages < 3:
                url = f"https://t.me/s/{handle}" + (f"?before={before}" if before else "")
                resp = await client.get(url)
                if resp.status_code != 200 or "tgme_widget_message" not in resp.text:
                    break
                msgs = parse_preview_page(resp.text)
                if not msgs:
                    break
                all_msgs = msgs + all_msgs
                pages += 1
                oldest = int(msgs[0]["post"].split("/")[-1])
                if watermark and oldest <= watermark:
                    break
                before = oldest
                if len(msgs) < 5:
                    break
        resp_text_marker = True
        msgs_all = all_msgs
        max_id = max((int(m["post"].split("/")[-1]) for m in all_msgs), default=watermark)
        if max_id > watermark:
            state["watermark"] = max_id
        if False:
            sources.mark_fetch(source["id"], False, f"preview unavailable: HTTP {resp.status_code}")
            summary["error"] = f"HTTP {resp.status_code}"
            return summary
        activated = parse_iso(source["activated_at"])
        for msg in msgs_all[:limit]:
            external_key = f"tgweb:{msg['post']}"
            mid_num = int(msg["post"].split("/")[-1])
            if items.exists(source["id"], external_key):
                summary["skipped"] += 1
                continue
            if watermark and mid_num <= watermark:
                summary["skipped"] += 1
                continue
            published = parse_iso(msg["published"])
            activation_ok = bool(activated is None or (published and published >= activated))
            title = msg["text"].split("\n", 1)[0][:200]
            fp = fingerprints_for(f"https://t.me/{msg['post'].replace('/', '/')}", title, msg["text"])
            items.insert(
                source_id=source["id"], platform="telegram", external_key=external_key,
                url=f"https://t.me/{msg['post']}", canonical_url=fp["canonical_url"],
                title=title, text=msg["text"], language=detect_language(msg["text"]),
                published_at=msg["published"], lineage_key=f"tgweb:{handle}",
                activation_ok=activation_ok, fingerprints=fp,
            )
            summary["new"] += 1
        sources.mark_fetch(source["id"], True, fetch_state=state)
        return summary
    except httpx.HTTPError as e:
        sources.mark_fetch(source["id"], False, f"transport: {e}"[:300])
        summary["error"] = str(e)
        return summary
