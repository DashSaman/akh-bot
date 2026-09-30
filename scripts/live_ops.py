"""Live operations: add owner-directed sources, force ingest, list fresh eligible items.

Run inside the container:  docker exec -i akhbot-app python - < scripts/live_ops.py [cmd]
Commands: add-sources | ingest | fresh
"""
import asyncio
import os
import sys

sys.path.insert(0, "/srv")
os.environ.setdefault("DATA_DIR", "/data")

from app.db.database import Database  # noqa: E402
from app.db.repo import RawItemsRepo, SourcesRepo  # noqa: E402

db = Database("/data/akhbot.db")

SOURCES = [
    ("UN News", "rss", "https://news.un.org/feed/subscribe/en/news/all/topics/news-en.xml",
     "", "en", "OFFICIAL_PRIMARY", True, True, "official_institution", 10),
    ("Al Jazeera", "rss", "https://www.aljazeera.com/xml/rss/all.xml",
     "", "en", "MAJOR_NEWSROOM", True, True, "news_organization", 6),
    ("DW Persian", "rss", "https://rss.dw.com/rdf/rss-per-all",
     "", "fa", "MAJOR_NEWSROOM", True, True, "news_organization", 6),
    ("Guardian World", "rss", "https://www.theguardian.com/world/rss",
     "", "en", "MAJOR_NEWSROOM", True, True, "news_organization", 10),
    ("IRNA", "rss", "https://www.irna.ir/rss",
     "", "fa", "LOCAL_SOURCE", True, True, "news_organization", 4),
    ("ISNA", "rss", "https://www.isna.ir/rss",
     "", "fa", "LOCAL_SOURCE", True, True, "news_organization", 4),
    ("tg withyashar", "telegram", "https://t.me/s/withyashar",
     "withyashar", "fa", "AGGREGATOR", False, False, "telegram_web_preview", 5),
    ("tg caronline", "telegram", "https://t.me/s/caronline",
     "caronline", "fa", "AGGREGATOR", False, False, "telegram_web_preview", 8),
    ("tg naya_foriraq", "telegram", "https://t.me/s/naya_foriraq",
     "naya_foriraq", "ar", "AGGREGATOR", False, False, "telegram_web_preview", 8),
]


def add_sources():
    repo = SourcesRepo(db)
    existing = {s["name"] for s in repo.list()}
    for name, platform, url, ext, lang, role, v, inc, stype, interval in SOURCES:
        if name in existing:
            continue
        sid = repo.create(name=name, platform=platform, url=url, external_id=ext,
                          language=lang, status="APPROVED", source_type=stype,
                          source_role=role, verification_allowed=v,
                          can_increase_independent_count=inc,
                          polling_interval_min=interval)
        print("added", sid, name, role)
    for s in repo.list():
        if s["name"] == "BBC Persian":  # owner Tier C monitor list
            repo.update(s["id"], verification_allowed=1,
                        source_role="MAJOR_NEWSROOM", polling_interval_min=6)
            repo.set_status(s["id"], "APPROVED")
            print("BBC Persian -> Tier C monitor")
    print("total:", len(repo.list()))


def ingest():
    from app.ingestion.scheduler import Scheduler

    s = Scheduler(db, type("S", (), {"telegram_ingest_ready": False})(), None, None)
    print("ingest:", asyncio.run(s.ingest_due()))


def fresh():
    rows = db.query(
        "SELECT r.id, r.source_id, s.name AS src, r.language, r.title, r.text, "
        "r.published_at, r.url FROM raw_items r JOIN sources s ON s.id=r.source_id "
        "WHERE r.activation_ok=1 AND r.processed_state='NEW' ORDER BY r.id DESC LIMIT 30")
    print("eligible fresh items:", len(rows))
    for r in rows:
        print(f"--- #{r['id']} [{r['src']}|{r['language']}] {r['published_at']}")
        print("   T:", r["title"][:110])
        print("   X:", (r["text"] or "")[:220].replace("\n", " "))
        print("   U:", r["url"])


if __name__ == "__main__":
    {"add-sources": add_sources, "ingest": ingest, "fresh": fresh}[sys.argv[1]]()
