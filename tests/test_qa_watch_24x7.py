import asyncio
import json
import pytest

from app.brand import Brand
from app.clustering.dedup import fingerprints_for
from app.db.repo import EventsRepo, PublicationsRepo, RawItemsRepo, SourcesRepo, StoriesRepo
from app.newsroom.qa_watch import _foreign_evidence, _story_issues, qa_pass
from app.newsroom.quality_gates import translation_lost_entities
from app.newsroom.translator import consistency_issues


SOURCE = "رصد عشرات الصواريخ اليمنية في سماء السعودية"
BAD_HEADLINE = "رصد عشرات موشک‌های یمنی در آسمان عربستان"
BAD_LEAD = "منابع نظامی از رصد دهها موشک یمنی در آسمان عربستان خبر دادند"
GOOD_HEADLINE = "ده‌ها موشک یمنی در آسمان عربستان رصد شدند"
GOOD_LEAD = "ده‌ها موشک یمنی در آسمان عربستان رصد شدند."
PUBLIC_BRAND = Brand({"name_fa":"آزمون", "tagline_fa":"خبر و بررسی", "telegram_handle":"test_news"})


def _seed_bad_story(db):
    sid = SourcesRepo(db).create(
        name="نایا", platform="telegram", url="https://t.me/s/naya_foriraq",
        language="ar", status="APPROVED",
    )
    fp = fingerprints_for("https://t.me/naya/1", SOURCE, SOURCE)
    rid = RawItemsRepo(db).insert(
        source_id=sid, platform="telegram", external_key="qa-1646",
        url="https://t.me/naya/1", canonical_url=fp["canonical_url"],
        title=SOURCE, text=SOURCE, language="ar", activation_ok=True,
        lineage_key="tg:naya", fingerprints=fp,
    )
    raw = RawItemsRepo(db).get(rid)
    event_id = EventsRepo(db).create(SOURCE, first_item=raw)
    draft = {
        "headline": BAD_HEADLINE,
        "lead": BAD_LEAD,
        "details": [],
        "source_names": "نایا",
        "platform_variants": {"telegram": BAD_HEADLINE},
        "generation_mode": "DETERMINISTIC",
        "language": "fa",
    }
    story_id = StoriesRepo(db).create(event_id, BAD_HEADLINE, BAD_LEAD, draft)
    db.execute("UPDATE stories SET lifecycle='PROVISIONAL' WHERE id=?", (story_id,))
    StoriesRepo(db).mark_published(story_id)
    pub_id = PublicationsRepo(db).upsert(story_id, "telegram", "old-hash", 1)
    PublicationsRepo(db).mark(pub_id, "SENT", remote_id="1646")
    db.execute("UPDATE publications SET chat_id='-1001' WHERE id=?", (pub_id,))
    return story_id


def test_1646_arabic_leak_and_invented_attribution_are_rejected():
    issues = _story_issues(SOURCE, BAD_HEADLINE, BAD_LEAD)
    assert "ARABIC_SOURCE_TOKEN_LEAK:عشرات" in issues
    assert "UNSUPPORTED_ATTRIBUTION:MILITARY_SOURCES" in issues
    assert _story_issues(SOURCE, GOOD_HEADLINE, GOOD_LEAD) == []


def test_qa_flags_mixed_script_and_cut_off_lead():
    issues = _story_issues(
        "A political impasse between the KRG and PUK threatens the region.",
        "اختلاف سیاسی کrg و پوک تهدید به تجزیه منطقه کردستان",
        "تشدید اختلاف سیاسی بین ح")
    assert "HOLD_TRANSLATION_QUALITY" in issues


def test_short_country_aliases_are_token_bounded():
    issues = translation_lost_entities(
        "Russia-Ukraine truce talks continue",
        "مذاکرات آتش‌بس روسیه و اوکراین ادامه دارد",
    )
    assert "country:بریتانیا" not in issues
    assert "country:آمریکا" not in issues


def test_foreign_evidence_includes_source_title_and_body(db):
    sid = SourcesRepo(db).create(
        name="aljazeera", platform="telegram", language="ar", status="APPROVED"
    )
    title = "اقتصاد غزة يتكبد خسائر فادحة بعد 3 سنوات من الحرب"
    body = "خلفت الحرب على غزة خسائر فادحة في القطاعات الاقتصادية"
    fp = fingerprints_for("https://example.test/gaza", title, body)
    rid = RawItemsRepo(db).insert(
        source_id=sid, platform="telegram", external_key="gaza-3y",
        title=title, text=body, language="ar", activation_ok=True,
        canonical_url=fp["canonical_url"], fingerprints=fp,
    )
    event_id = EventsRepo(db).create(title, first_item=RawItemsRepo(db).get(rid))
    evidence = _foreign_evidence(db, event_id)
    assert evidence and title in evidence["evidence"] and body in evidence["evidence"]
    assert "3" in evidence["evidence"]


def test_qa_watch_dry_run_flags_recent_sent_story(db, settings):
    _seed_bad_story(db)
    stats = asyncio.run(qa_pass(
        db, settings, None, None, window_minutes=180, dry_run=True
    ))
    assert stats["checked"] == 1
    assert stats["flagged"] == 1
    assert stats["repaired"] == 0


def test_qa_watch_repairs_same_telegram_message(db, settings):
    story_id = _seed_bad_story(db)

    class Router:
        available = True

        async def chat_json(self, **kwargs):
            result = {"headline": GOOD_HEADLINE, "lead": GOOD_LEAD}
            validator = kwargs.get("validator")
            assert validator is None or validator(result)
            return result

    stats = asyncio.run(qa_pass(
        db, settings, PUBLIC_BRAND, Router(),
        window_minutes=180, dry_run=False,
    ))

    assert stats["flagged"] == 1
    assert stats["repaired"] == 1
    jobs = db.query("SELECT * FROM jobs WHERE job_type='publish_edit'")
    assert len(jobs) == 1
    payload = json.loads(jobs[0]["payload_json"])
    assert payload["story_id"] == story_id
    assert GOOD_HEADLINE in payload["text"]

    story = StoriesRepo(db).get(story_id)
    assert story["headline"] == GOOD_HEADLINE
    assert story["lead"] == GOOD_LEAD
    draft = json.loads(story["draft_json"])
    assert draft["generation_mode"] == "QA_REPAIR"

    pubs = db.query(
        "SELECT * FROM publications WHERE story_id=? ORDER BY id",
        (story_id,),
    )
    assert len(pubs) == 2
    assert pubs[0]["status"] == "SENT" and pubs[0]["remote_id"] == "1646"
    assert pubs[-1]["status"] == "PENDING"


def test_failed_qa_repair_holds_internally_without_public_notice(db, settings):
    story_id = _seed_bad_story(db)
    stats = asyncio.run(qa_pass(db, settings, PUBLIC_BRAND, None))
    assert stats["held"] == 1
    assert db.query("SELECT * FROM jobs") == []
    story = StoriesRepo(db).get(story_id)
    event = EventsRepo(db).get(story["event_id"])
    assert event["status"] == "HELD"
    assert event["quality_hold"] == "HOLD_TRANSLATION_QUALITY"
    assert len(db.query("SELECT * FROM publications")) == 1


@pytest.mark.parametrize("repair_available", [True, False])
def test_qa_discards_result_if_story_advanced_during_translation(db, settings, repair_available):
    story_id = _seed_bad_story(db)
    latest = "وزارت خارجه ایران اعلام کرد مذاکرات تازه در تهران ادامه دارد."
    class Router:
        available = True
        async def chat_json(self, **kwargs):
            db.execute("UPDATE stories SET version=5,headline=? WHERE id=?", (latest,story_id))
            db.execute("UPDATE events SET status='PUBLISHED' WHERE id=1")
            return {"headline": GOOD_HEADLINE,"lead": GOOD_LEAD} if repair_available else None
    asyncio.run(qa_pass(db,settings,PUBLIC_BRAND,Router()))
    story=StoriesRepo(db).get(story_id)
    assert story["version"] == 5
    assert story["headline"] == latest
    assert EventsRepo(db).get(story["event_id"])["status"] == "PUBLISHED"
    assert db.query("SELECT * FROM jobs") == []
