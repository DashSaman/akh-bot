"""Activate registry endpoints truthfully (§7/§17) + staged rollout.

1. Discovered direct RSS feeds (discover_feeds.py output) → convert the
   Website endpoint to an ACTIVE rss endpoint (feed URL).
2. Bot-protected newsroom websites → a PUBLIC Google News RSS search feed
   for that outlet (official public endpoint; NOT a paywall/robots bypass —
   we ingest only what the feed publishes). Identity stays the outlet's
   Entity ID so independence semantics are unchanged.
3. Non-newsroom websites (official docs, OSINT data pages, people) stay
   UNSUPPORTED — truthful.

Usage (inside container):
  python /tmp/activate.py [--google-news] [--stage N]
Stages: 1=direct feeds + telegram, 2=+google-news feeds
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import quote, urlsplit

NEWSROOM_KINDS = ("newsroom", "news agency", "iran-focused", "media",
                  "newspaper", "broadcaster")


def _is_newsroom(kind: str, trust: str) -> bool:
    k = (kind or "").lower()
    t = (trust or "").lower()
    if any(n in k for n in NEWSROOM_KINDS):
        return True
    return "newsroom" in t or "media" in t


def google_news_feed(site_url: str, lang: str) -> str:
    domain = urlsplit(site_url).netloc.replace("www.", "")
    hl = {"fa": "fa", "ar": "ar", "he": "he"}.get(lang[:2], "en")
    q = quote(f"site:{domain} when:2d")
    return (f"https://news.google.com/rss/search?q={q}"
            f"&hl={hl}&gl={hl}&ceid={hl}:{hl}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/data/akhbot.db")
    ap.add_argument("--feeds", default="/tmp/feeds.json")
    ap.add_argument("--google-news", action="store_true")
    ap.add_argument("--stage", type=int, default=1)
    args = ap.parse_args()

    sys.path.insert(0, "/srv")
    from app.db.database import Database
    from app.db.repo import SourcesRepo

    db = Database(args.db)
    repo = SourcesRepo(db)
    stats = {"direct": 0, "google_news": 0, "kept_unsupported": 0}

    # 1) direct discovered feeds
    feeds = {}
    try:
        feeds = json.load(open(args.feeds, encoding="utf-8"))
    except (OSError, ValueError):
        pass
    for sid_str, info in feeds.items():
        if not info.get("feeds"):
            continue
        sid = int(sid_str)
        src = repo.get(sid)
        if not src or src["platform"] != "website":
            continue
        repo.update(sid, platform="rss", url=info["feeds"][0],
                    source_type="rss_feed", endpoint_state="ACTIVE")
        stats["direct"] += 1

    # 2) google-news public search feeds for bot-protected newsrooms
    if args.google_news or args.stage >= 2:
        for src in db.query(
                "SELECT * FROM sources WHERE platform='website'"
                " AND endpoint_state='UNSUPPORTED'"):
            if not _is_newsroom(
                    (src.get("role_detail") or ""), src.get("notes") or "") \
                    and not _is_newsroom(src.get("focus") or "", ""):
                # kind lives in notes via trust_use; use name heuristic too
                pass
            kind_hint = (src["notes"] or "") + " " + (src["focus"] or "")
            if not _is_newsroom(kind_hint, kind_hint):
                stats["kept_unsupported"] += 1
                continue
            feed = google_news_feed(src["url"], src["language"] or "en")
            # convert the website row itself into the public-feed endpoint
            repo.update(src["id"], platform="rss", url=feed,
                        source_type="rss_feed_google_news",
                        endpoint_state="ACTIVE")
            stats["google_news"] += 1

    print("activation:", stats)
    by_state = {r["endpoint_state"]: r["c"] for r in db.query(
        "SELECT endpoint_state, COUNT(*) AS c FROM sources WHERE identity!=''"
        " GROUP BY endpoint_state")}
    print("endpoint states:", by_state)
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
