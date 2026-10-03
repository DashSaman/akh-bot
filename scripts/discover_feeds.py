"""Legitimate RSS/Atom feed discovery for Website endpoints (§7: prefer
official API → RSS/Atom → ... → public webpage).

Fetches each site's homepage ONCE (bounded, standard UA, 15s timeout) and
parses <link rel="alternate" type="application/rss+xml|atom+xml">. No
paywall/login/CAPTCHA bypass — anything requiring auth stays UNSUPPORTED.

Run on the server:  python scripts/discover_feeds.py [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (compatible; akhbot/0.1; +https://t.me/RastehNews)"}

_LINK_RE = re.compile(
    r"<link[^>]+rel=[\"']alternate[\"'][^>]*>", re.I)
_HREF_RE = re.compile(r"href=[\"']([^\"']+)[\"']", re.I)
_TYPE_RE = re.compile(r"type=[\"'](application/(?:rss|atom)\+xml)[\"']", re.I)


def discover_feeds(html: str, base_url: str) -> list[str]:
    feeds: list[str] = []
    for tag in _LINK_RE.findall(html or ""):
        if not _TYPE_RE.search(tag):
            continue
        m = _HREF_RE.search(tag)
        if not m:
            continue
        href = m.group(1)
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            root = re.match(r"(https?://[^/]+)", base_url)
            href = root.group(1) + href if root else href
        elif not href.startswith("http"):
            continue
        if href not in feeds:
            feeds.append(href)
    return feeds[:3]


def main() -> int:
    import asyncio

    import httpx

    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/data/akhbot.db")
    ap.add_argument("--out", default="/data/discovered_feeds.json")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    from app.db.database import Database

    db = Database(args.db)
    sites = db.query(
        "SELECT id, identity, name, url FROM sources"
        " WHERE platform='website' AND endpoint_state='UNSUPPORTED' LIMIT ?",
        (args.limit,))
    print(f"discovering feeds for {len(sites)} websites")

    async def run() -> dict[str, list[dict]]:
        results: dict[str, list] = {}
        sem = __import__("asyncio").Semaphore(5)  # polite concurrency

        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                     headers=UA) as client:
            async def probe(site):
                async with sem:
                    try:
                        r = await client.get(site["url"])
                        feeds = discover_feeds(r.text, str(r.url)) if r.status_code == 200 else []
                        status = r.status_code
                    except Exception as ex:  # noqa: BLE001
                        feeds, status = [], str(ex)[:60]
                results[str(site["id"])] = {
                    "identity": site["identity"], "name": site["name"],
                    "site": site["url"], "http": status, "feeds": feeds}

            await asyncio.gather(*(probe(s) for s in sites))
        return results

    results = asyncio.run(run())
    Path(args.out).write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    n_feeds = sum(1 for v in results.values() if v["feeds"])
    print(f"discovered feeds for {n_feeds}/{len(results)} sites -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
