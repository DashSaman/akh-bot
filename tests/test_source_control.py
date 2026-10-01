"""Owner-controlled source system: allowlist, policy gate, rank, seconds polling."""
import asyncio

from app.db.repo import EventsRepo, RawItemsRepo, SourcesRepo

from app.newsroom.pipeline import process_new_items

A = "تمرین نظامی مشترک دو کشور در مرز شرقی آغاز شد و گزارش‌های اولیه حاکی از حضور یگان‌های ویژه است"
BODY_A = A + ". ستاد خبری منبع رسمی جزئیات بیشتری درباره شرح مانور اعلام کرد."
BODY_B = A + ". دیپلمات‌های منطقه نیز از تداوم همکاری‌های دفاعی دو طرف خبر دادند."


def _add(db, sid, key, title, text, lineage):
    from app.clustering.dedup import fingerprints_for

    fp = fingerprints_for(f"https://it{key}.example/{key}", title, text)
    return RawItemsRepo(db).insert(
        source_id=sid, platform="rss", external_key=key,
        url=f"https://it{key}.example/{key}", canonical_url=fp["canonical_url"],
        title=title, text=text, language="fa", published_at="2030-01-01T00:00:00+00:00",
        activation_ok=True, lineage_key=lineage, fingerprints=fp)


class S:
    telegram_publish_ready = False
    max_llm_calls_per_minute = 30
    max_llm_calls_per_hour = 500


def test_discovery_only_source_cannot_create_public_story(db):
    s1 = SourcesRepo(db).create(name="watch", platform="rss", url="u", status="APPROVED",
                                publication_policy="DISCOVERY_ONLY")
    _add(db, s1, "a", "آغاز تمرین نظامی مرزی", BODY_A, "dom:w")
    asyncio.run(process_new_items(db, None, None, S()))
    e = EventsRepo(db).list()[0]
    assert e["status"] == "HELD"  # discovery-only: investigation, no publication


def test_auto_source_publishes_and_discovery_corroborates(db):
    s1 = SourcesRepo(db).create(name="auto", platform="rss", url="u1", status="APPROVED",
                                publication_policy="DISCOVERY_ONLY")
    _add(db, s1, "a", "آغاز تمرین نظامی مرزی", BODY_A, "dom:w")
    asyncio.run(process_new_items(db, None, None, S()))
    s2 = SourcesRepo(db).create(name="auto2", platform="rss", url="u2", status="APPROVED",
                                publication_policy="AUTO", verification_allowed=True)
    _add(db, s2, "b", "آغاز تمرین نظامی مرزی", BODY_B, "dom:a")
    asyncio.run(process_new_items(db, None, None, S()))
    e = EventsRepo(db).list()[0]
    story = db.query_one("SELECT * FROM stories WHERE event_id=?", (e["id"],))
    assert story, "AUTO source enables publication; discovery-only only corroborates"


def test_due_uses_seconds_and_allowlist_order(db):
    from datetime import datetime, timezone

    SourcesRepo(db).create(name="low", platform="rss", url="u", status="APPROVED",
                           priority_rank=10, polling_interval_seconds=120)
    SourcesRepo(db).create(name="t1", platform="rss", url="u2", status="APPROVED",
                           priority_rank=1, polling_interval_seconds=30)
    off = SourcesRepo(db).create(name="off", platform="rss", url="u3", status="APPROVED",
                                 priority_rank=2)
    SourcesRepo(db).update(off, enabled=0)
    due = SourcesRepo(db).due(datetime.now(timezone.utc))
    names = [s["name"] for s in due]
    assert names == ["t1", "low"]  # rank order; disabled excluded


def test_policy_values_persist(db):
    sid = SourcesRepo(db).create(name="x", platform="rss", url="u", status="APPROVED",
                                 publication_policy="NEVER_PUBLISH", priority_rank=3,
                                 polling_interval_seconds=45)
    row = SourcesRepo(db).get(sid)
    assert row["publication_policy"] == "NEVER_PUBLISH"
    assert row["priority_rank"] == 3 and row["polling_interval_seconds"] == 45
