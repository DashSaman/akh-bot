"""Source trust policy: TECHNICALLY_ENABLED ≠ EDITORIALLY_APPROVED.

Ingestion approval (APPROVED) enables collection only. Verification trust is a
separate owner-granted flag. Aggregators never add independent origins.
Two reports corroborate a claim when they share the key line but come from
different origins (verbatim copies dedup away and must NOT count).
"""
import asyncio

from app.db.repo import ClaimsRepo, EventsRepo, RawItemsRepo, SourcesRepo
from app.newsroom.pipeline import llm_budget_ok, process_new_items

SHARED = "سی‌ودومین نمایشگاه کتاب تهران امروز با حضور ناشران داخلی بازگشایی شد"
BODY_A = SHARED + ". بازدید عمومی تا پایان هفته ادامه دارد و غرفه‌های ناشران در سالن اصلی آماده دیدار است."
BODY_B = SHARED + ". در حاشیه این رویداد فرهنگی چند نشست تخصصی نشر و برنامه‌های کودک برگزار خواهد شد."


def _add(db, sid, key, title, text, lineage):
    from app.clustering.dedup import fingerprints_for

    fp = fingerprints_for(f"https://it{key}.example/{key}", title, text)
    return RawItemsRepo(db).insert(
        source_id=sid, platform="rss", external_key=key,
        url=f"https://it{key}.example/{key}", canonical_url=fp["canonical_url"],
        title=title, text=text, language="fa", published_at="2030-01-01T00:00:00+00:00",
        activation_ok=True, lineage_key=lineage, fingerprints=fp,
    )


def _two_source_event(db, *, v1: bool, v2: bool):
    """Same headline (same event, stage-3), distinct bodies/origins (real outlets)."""
    s1 = SourcesRepo(db).create(name="s1", platform="rss", url="u1", status="APPROVED",
                                verification_allowed=v1)
    s2 = SourcesRepo(db).create(name="s2", platform="rss", url="u2", status="APPROVED",
                                verification_allowed=v2)
    _add(db, s1, "a", "بازگشایی نمایشگاه کتاب تهران", BODY_A, "dom:a")
    _add(db, s2, "b", "بازگشایی نمایشگاه کتاب تهران", BODY_B, "dom:b")


def test_owner_approved_sources_corroborate(db):
    _two_source_event(db, v1=True, v2=True)
    asyncio.run(process_new_items(db, None, None, None))
    e = EventsRepo(db).list()[0]
    claims = ClaimsRepo(db).for_event(e["id"])
    assert any(c["state"] == "CORROBORATED" for c in claims), [c["state"] for c in claims]


def test_technical_source_never_corroborates(db):
    """Both sources TECHNICAL (verification_allowed=0) → claims stay UNVERIFIED."""
    _two_source_event(db, v1=False, v2=False)
    asyncio.run(process_new_items(db, None, None, None))
    e = EventsRepo(db).list()[0]
    claims = ClaimsRepo(db).for_event(e["id"])
    assert claims
    assert all(c["state"] in ("UNVERIFIED", "SINGLE_SOURCE") for c in claims), \
        [c["state"] for c in claims]


def test_mixed_trust_only_counts_approved_origins(db):
    """One approved + one technical → single trusted origin → not CORROBORATED."""
    _two_source_event(db, v1=True, v2=False)
    asyncio.run(process_new_items(db, None, None, None))
    e = EventsRepo(db).list()[0]
    claims = ClaimsRepo(db).for_event(e["id"])
    assert all(c["state"] != "CORROBORATED" for c in claims)


def test_new_sources_default_to_not_verification_approved(db):
    sid = SourcesRepo(db).create(name="x", platform="rss", url="u", status="APPROVED")
    assert SourcesRepo(db).get(sid)["verification_allowed"] == 0


def test_aggregator_never_increases_independent_count(db):
    s1 = SourcesRepo(db).create(name="primary", platform="rss", url="u1",
                                status="APPROVED", verification_allowed=True)
    agg = SourcesRepo(db).create(name="agg", platform="telegram", url="u2",
                                 status="APPROVED", source_role="AGGREGATOR",
                                 verification_allowed=True,
                                 can_increase_independent_count=False)
    _add(db, s1, "a", "برگزاری همایش ملی هواشناسی", "دوازدهمین همایش ملی هواشناسی با حضور کارشناسان امروز آغاز به کار کرد و گزارش‌هایی از حضور سخنرانان مطرح منتشر شده است", "dom:p")
    _add(db, agg, "b", "برگزاری همایش ملی هواشناسی", "دوازدهمین همایش ملی هواشناسی با حضور کارشناسان امروز آغاز به کار کرد و پوشش خبری گسترده‌ای در رسانه‌ها همراه بود", "dom:p")
    asyncio.run(process_new_items(db, None, None, None))
    e = EventsRepo(db).list()[0]
    assert e["report_count"] == 2
    assert e["independent_count"] == 1  # aggregator origin collapsed by flag


def test_llm_budget_guard_blocks_calls(db):
    class S:  # tight budget
        max_llm_calls_per_minute = 1
        max_llm_calls_per_hour = 500

    from app.db.repo import utcnow

    db.execute(
        "INSERT INTO llm_cache(cache_key,response_json,model,prompt_version,created_at)"
        " VALUES('k','{}','m','v',?)", (utcnow(),))
    assert llm_budget_ok(db, S()) is False
    assert llm_budget_ok(db, None) is True  # no settings → no guard

    class Off:
        max_llm_calls_per_minute = 0  # disabled
        max_llm_calls_per_hour = 0

    assert llm_budget_ok(db, Off()) is True
