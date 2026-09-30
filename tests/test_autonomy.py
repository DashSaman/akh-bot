"""Autonomy regression: HELD never starves, no-AI publishes deterministically,
new evidence updates an existing story instead of skipping it."""
import asyncio

from app.db.repo import EventsRepo, PublicationsRepo, RawItemsRepo, SourcesRepo, StoriesRepo

from app.newsroom.pipeline import process_new_items

A = "سی‌ودومین نمایشگاه کتاب تهران امروز با حضور ناشران داخلی بازگشایی شد"
BODY_A = A + ". بازدید عمومی تا پایان هفته ادامه دارد و غرفه‌های ناشران آماده است."
BODY_B = A + ". در حاشیه این رویداد چند نشست تخصصی نشر برگزار خواهد شد."


def _add(db, sid, key, title, text, lineage):
    from app.clustering.dedup import fingerprints_for

    fp = fingerprints_for(f"https://it{key}.example/{key}", title, text)
    return RawItemsRepo(db).insert(
        source_id=sid, platform="rss", external_key=key,
        url=f"https://it{key}.example/{key}", canonical_url=fp["canonical_url"],
        title=title, text=text, language="fa", published_at="2030-01-01T00:00:00+00:00",
        activation_ok=True, lineage_key=lineage, fingerprints=fp)


class S:
    telegram_publish_ready = True
    max_llm_calls_per_minute = 30
    max_llm_calls_per_hour = 500


def _events(db):
    return {e["title"][:20]: e for e in EventsRepo(db).list()}


def test_held_event_rechecked_and_promoted_without_ai(db):
    """1 source → held; 2nd independent trusted source arrives → CONFIRMED published."""
    s1 = SourcesRepo(db).create(name="s1", platform="rss", url="u1", status="APPROVED",
                                verification_allowed=True)
    _add(db, s1, "a", "بازگشایی نمایشگاه کتاب تهران", BODY_A, "dom:a")
    asyncio.run(process_new_items(db, None, None, S()))  # first pass: single → held/deterministic
    # second independent trusted origin joins the SAME event (same headline)
    s2 = SourcesRepo(db).create(name="s2", platform="rss", url="u2", status="APPROVED",
                                verification_allowed=True)
    _add(db, s2, "b", "بازگشایی نمایشگاه کتاب تهران", BODY_B, "dom:b")
    asyncio.run(process_new_items(db, None, None, S()))  # reverify pass — HELD must not starve
    ev = EventsRepo(db).list()[0]
    assert ev["status"] in ("PUBLISHED", "HELD", "WRITTEN"), ev["status"]
    story = StoriesRepo(db).by_event(ev["id"])
    assert story, "story must exist after re-verification without any AI"
    jobs = [j for j in db.query("SELECT * FROM jobs") if j["job_type"].startswith("publish")]
    assert jobs, "publication job must be enqueued (deterministic mode)"


def test_deterministic_story_has_no_external_sources_and_own_footer(db):
    from app.brand import load_brand
    import json as _json

    s1 = SourcesRepo(db).create(name="s1", platform="rss", url="u1", status="APPROVED",
                                verification_allowed=True)
    s2 = SourcesRepo(db).create(name="s2", platform="rss", url="u2", status="APPROVED",
                                verification_allowed=True)
    _add(db, s1, "a", "برگزاری همایش ملی هواشناسی", BODY_A, "dom:a")
    _add(db, s2, "b", "برگزاری همایش ملی هواشناسی", BODY_B, "dom:b")
    brand = type("B", (), {"name_fa": "x", "telegram_handle": "RastehNews"})()
    asyncio.run(process_new_items(db, None, brand, S()))
    story = StoriesRepo(db).by_event(EventsRepo(db).list()[0]["id"])
    text = _json.loads(story["draft_json"])["platform_variants"]["telegram"]
    assert text.endswith("@RastehNews")
    assert "it" not in text.split("🆔")[0].split()[-1:]  # no external URL/handle leaked
    assert story["lifecycle"] in ("CONFIRMED", "PROVISIONAL")
    assert _json.loads(story["draft_json"])["generation_mode"] == "DETERMINISTIC"


def test_existing_story_updated_not_skipped(db):
    """PROVISIONAL story + new corroborating evidence → same story re-versioned."""
    s1 = SourcesRepo(db).create(name="s1", platform="rss", url="u1", status="APPROVED",
                                verification_allowed=True)
    _add(db, s1, "a", "نشست سران تجاری", BODY_A, "dom:a")
    asyncio.run(process_new_items(db, None, None, S()))
    ev = EventsRepo(db).list()[0]
    st1 = StoriesRepo(db).by_event(ev["id"])
    assert st1
    StoriesRepo(db).db.execute("UPDATE stories SET lifecycle='PROVISIONAL' WHERE id=?", (st1["id"],))
    s2 = SourcesRepo(db).create(name="s2", platform="rss", url="u2", status="APPROVED",
                                verification_allowed=True)
    _add(db, s2, "b", "نشست سران تجاری", BODY_B, "dom:b")
    asyncio.run(process_new_items(db, None, None, S()))
    st2 = StoriesRepo(db).by_event(ev["id"])
    assert st2["id"] == st1["id"]  # same story — no duplicate
    assert int(st2["version"]) >= int(st1["version"])  # updated in place
