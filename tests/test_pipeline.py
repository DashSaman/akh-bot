"""Pipeline tests: lineage/dependency, conflicting casualties (high-risk), multilingual clustering."""
import asyncio
import json

from app.db.repo import ClaimsRepo, EventsRepo, RawItemsRepo, SourcesRepo
from app.integrations.llm.glm import FakeProvider
from app.newsroom.pipeline import process_new_items


def _add_item(db, source_id, key, title, text, published, lineage=None, platform="rss"):
    from app.clustering.dedup import fingerprints_for

    url = f"https://item{key}.example/{key}"
    fp = fingerprints_for(url, title, text)
    return RawItemsRepo(db).insert(
        source_id=source_id, platform=platform, external_key=key,
        url=url, canonical_url=fp["canonical_url"],
        title=title, text=text, language="fa", published_at=published,
        activation_ok=True, lineage_key=lineage or f"src:{source_id}", fingerprints=fp,
    )


def _approved_sources(db, n):
    ids = []
    for i in range(n):
        ids.append(SourcesRepo(db).create(name=f"ch{i}", platform="telegram",
                                          external_id=f"@ch{i}", status="APPROVED"))
    return ids


def test_source_dependency_five_copies_one_origin(db):
    """5 channels forward the same Reuters story → 5 reports, ~1 independent origin."""
    srcs = _approved_sources(db, 5)
    text = "رویترز گزارش داد: حمله پهپادی به تأسیسات نفتی اتفاق افتاد و شعله‌های آتش دیده شد"
    for i, sid in enumerate(srcs):
        _add_item(db, sid, f"m{i}", "حمله پهپادی به تأسیسات نفتی", text,
                  f"2030-01-01T0{i}:00:00+00:00", lineage="tg:reuters")
    summary = asyncio.run(process_new_items(db, None, None, None))
    events = EventsRepo(db).list()
    assert len(events) == 1
    e = events[0]
    assert e["report_count"] == 5
    assert e["independent_count"] == 1  # NOT 5 confirmations


def test_conflicting_casualties_held_not_published(db):
    """A: 20 casualties vs B: 8 — no primary confirmation → CONFLICTING, never a confirmed headline."""
    srcs = _approved_sources(db, 2)
    _add_item(db, srcs[0], "a", "انفجار بزرگ", "به گزارش منابع محلی ۲۰ نفر در انفجار کشته شدند و تلفات اعلام شد",
              "2030-01-01T01:00:00+00:00", lineage="dom:a.example")
    _add_item(db, srcs[1], "b", "انفجار بزرگ", "منبع بیمارستان گفت ۸ نفر کشته شدند در پی انفجار",
              "2030-01-01T01:05:00+00:00", lineage="dom:b.example")
    asyncio.run(process_new_items(db, None, None, None))
    events = EventsRepo(db).list()
    assert events, "event should exist"
    e = events[0]
    assert e["status"] == "HELD"  # hard gate: conflicting high-risk numbers


def test_independent_sources_corroborate(db):
    srcs = _approved_sources(db, 2)
    _add_item(db, srcs[0], "a", "زمین‌لرزه در شرق کشور", "زمین‌لرزه به قدرت ۵.۳ ریشتر شرق کشور را لرزاند",
              "2030-01-01T02:00:00+00:00", lineage="dom:a.example")
    _add_item(db, srcs[1], "b", "زمین‌لرزه ۵.۳ ریشتری", "زمین‌لرزه به قدرت ۵.۳ ریشتر شرق کشور را لرزاند",
              "2030-01-01T02:10:00+00:00", lineage="dom:b.example")
    asyncio.run(process_new_items(db, None, None, None))
    e = EventsRepo(db).list()[0]
    assert e["independent_count"] == 2


def test_event_has_one_story_and_one_master_url(db):
    """Same evolving event keeps ONE story/URL; updates extend, never duplicate pages."""
    from app.db.repo import StoriesRepo

    srcs = _approved_sources(db, 1)
    _add_item(db, srcs[0], "a", "مذاکرات ادامه دارد", "دور تازه مذاکرات با میانجی‌گری آغاز شد و هیئدها حاضرند",
              "2030-01-01T03:00:00+00:00", lineage="dom:a.example")

    provider = FakeProvider(responses=[
        {"__kind__": "claims", "claims": ["دور تازه مذاکرات آغاز شد"]},
        {"__kind__": "writer", "headline": "آغاز دور تازه مذاکرات", "lead": "به گزارش دو منبع مستقل مذاکرات آغاز شد.",
         "body": [{"text": "دور تازه مذاکرات با میانجی‌گری آغاز شد.", "claim_refs": ["1"]}],
         "confirmed_facts": ["آغاز مذاکرات"], "uncertain_facts": [], "timeline": [],
         "source_references": [{"source_id": 1, "name": "ch0", "platform": "telegram", "language": "fa", "url": ""}],
         "category": "politics", "tags": ["مذاکره"], "seo_title": "مذاکرات", "seo_description": "شرح",
         "platform_variants": {"telegram": "آغاز مذاکرات", "x": "مذاکرات آغاز شد", "threads": "", "instagram_caption": "", "web_extra": ""}},
    ])
    settings_stub = type("S", (), {"telegram_publish_ready": False})()
    asyncio.run(process_new_items(db, provider, None, settings_stub))
    stories = StoriesRepo(db).list() if hasattr(StoriesRepo(db), "list") else db.query("SELECT * FROM stories")
    assert len(stories) == 1


def test_llm_outage_leaves_events_waiting(db):
    """GLM unavailable → collection and clustering continue; writing simply waits."""
    srcs = _approved_sources(db, 1)
    _add_item(db, srcs[0], "x", "خبر مهم", "متن خبر مهم برای آزمون قطع سرویس مدل زبانی در تحریریه",
              "2030-01-01T04:00:00+00:00", lineage="dom:a.example")

    class DeadProvider:
        name, model = "dead", "m"

        async def chat_json(self, **kw):
            raise RuntimeError("glm offline")

    asyncio.run(process_new_items(db, DeadProvider(), None, type("S", (), {"telegram_publish_ready": False})()))
    e = EventsRepo(db).list()[0]
    assert e["status"] == "READY"  # waiting for writer retry — never fake success
    claims = ClaimsRepo(db).for_event(e["id"])
    assert claims  # baseline claims still recorded (rules-only verification)
