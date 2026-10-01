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


def test_disabled_source_pending_job_cancelled_at_execution(db):
    """Old queued job from a now-disabled source must NOT publish."""
    import httpx

    from app.core.textnorm import sha256_hex
    from app.db.repo import EventsRepo, PublicationsRepo, JobsRepo, StoriesRepo
    from app.jobs.runner import make_publish_handler

    sid = SourcesRepo(db).create(name="was-on", platform="rss", url="u", status="APPROVED")
    db.execute("INSERT INTO events(title,status,first_seen_at,last_seen_at) VALUES('e','NEW','2030-01-01','2030-01-01')")
    eid = db.query_one("SELECT last_insert_rowid() i")["i"]
    db.execute("INSERT INTO raw_items(source_id,platform,external_key,fetched_at,activation_ok) VALUES(?,?,?,?,1)",
               (sid, "rss", "k", "2030-01-01"))
    iid = db.query_one("SELECT last_insert_rowid() i")["i"]
    db.execute("INSERT INTO event_items(event_id,raw_item_id) VALUES(?,?)", (eid, iid))
    st = StoriesRepo(db).create(eid, "تیتر", "لید", {"platform_variants": {"telegram": "متن"}})
    # owner later DISABLES this source
    SourcesRepo(db).update(sid, enabled=0, source_control_state="OWNER_DISABLED")

    sent = {"n": 0}

    def tr(request):
        sent["n"] += 1
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 9}})

    h = make_publish_handler(db, type("S", (), {
        "max_posts_per_hour": 100, "max_posts_per_day": 100,
        "max_provisional_posts_per_hour": 100, "max_confirmed_posts_per_hour": 100,
        "telegram_publish_target": "-1004459746525"})(),
        lambda: __import__("app.publishing.telegram_bot", fromlist=["TelegramBotPublisher"]).TelegramBotPublisher(
            "t", "-1004459746525", transport=httpx.MockTransport(tr)))
    import asyncio

    ok = asyncio.run(h({"story_id": st, "platform": "telegram",
                        "payload_hash": sha256_hex("x"), "text": "متن"}))
    assert ok is True and sent["n"] == 0  # cancelled, never sent
    row = PublicationsRepo(db).list()[0]
    assert row["status"] == "SKIPPED" and "SOURCE_DISABLED" in (row["error"] or "")


def test_source_display_names_from_event_evidence(db):
    from app.newsroom.pipeline import source_display_names

    sid = SourcesRepo(db).create(name="tg naya_foriraq", platform="telegram", external_id="n", status="APPROVED")
    db.execute("INSERT INTO events(title,status,first_seen_at,last_seen_at) VALUES('e','NEW','2030-01-01','2030-01-01')")
    eid = db.query_one("SELECT last_insert_rowid() i")["i"]
    db.execute("INSERT INTO raw_items(source_id,platform,external_key,fetched_at,activation_ok) VALUES(?,?,?,?,1)", (sid, "telegram", "k", "2030-01-01"))
    iid = db.query_one("SELECT last_insert_rowid() i")["i"]
    db.execute("INSERT INTO event_items(event_id,raw_item_id) VALUES(?,?)", (eid, iid))
    assert source_display_names(db, eid) == "نایا"
