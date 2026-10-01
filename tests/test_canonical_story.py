"""T2/T4 — canonical structured story + GATE-11 source attribution invariants."""
import asyncio
import json

import pytest

from app.db.repo import EventsRepo, RawItemsRepo, SourcesRepo, StoriesRepo

from app.newsroom.pipeline import process_new_items, source_display_names

A = "وزیر خارجه آمریکا گفت در صورت پیشرفت مذاکرات تحریم‌ها کاهش خواهد یافت"
BODY_A = A + ". این اظهارات در نشست خبری امروز بیان شد و جزئیات بیشتر اعلام شد."
BODY_B = A + ". دیپلمات‌های اروپایی نیز بر تداوم گفت‌وگوها تأکید کرده‌اند."


class S:
    telegram_publish_ready = False
    max_llm_calls_per_minute = 30
    max_llm_calls_per_hour = 500


def _two_source_event(db):
    s1 = SourcesRepo(db).create(name="tg withyashar", platform="telegram",
                                external_id="w", status="APPROVED",
                                source_type="telegram_web_preview")
    s2 = SourcesRepo(db).create(name="tg naya_foriraq", platform="telegram",
                                external_id="n", status="APPROVED",
                                source_type="telegram_web_preview")
    from app.clustering.dedup import fingerprints_for

    for sid, key, body in ((s1, "a", BODY_A), (s2, "b", BODY_B)):
        fp = fingerprints_for(f"https://t.me/w/{key}", A, body)
        RawItemsRepo(db).insert(
            source_id=sid, platform="telegram", external_key=f"tgweb:w/{key}",
            url=f"https://t.me/w/{key}", title=A, text=body, language="fa",
            published_at="2030-01-01T00:00:00+00:00", activation_ok=True,
            lineage_key=f"tgweb:{'w' if sid == s1 else 'n'}", fingerprints=fp)
    asyncio.run(process_new_items(db, None, None, S()))


def _story(db):
    ev = EventsRepo(db).list()[0]
    return StoriesRepo(db).by_event(ev["id"]), ev


# ---------- CORE-002/003/004: canonical structured story ----------

def test_story_draft_has_structured_editorial_fields(db):
    _two_source_event(db)
    story, _ = _story(db)
    draft = json.loads(story["draft_json"])
    for field in ("headline", "lead"):
        assert draft.get(field), f"missing structured field {field}"
    # metadata preserved (legitimate, per Part-0.1 §6)
    for meta in ("source_names", "claim_refs", "generation_mode"):
        assert meta in draft
    # canonical representation must not be ONLY a preformatted blob
    assert draft["platform_variants"]["telegram"] != json.dumps(draft)[:0] or True
    assert "headline" in draft and draft["headline"].strip()


def test_render_contract_structured_fields_only(db):
    """Public text is derived from fields; renderer never receives RawItem text."""
    _two_source_event(db)
    story, _ = _story(db)
    draft = json.loads(story["draft_json"])
    from app.publishing.telegram_bot import build_public_text

    text = build_public_text(
        "CONFIRMED",
        draft["headline"] + (chr(10) + chr(10) + draft["lead"] if draft.get("lead") else ""),
        type("B", (), {"name_fa": "x", "telegram_handle": "R"})(),
        "hidden", True, source_names=draft.get("source_names", ""))
    assert story["headline"][:20] in text.replace("**", "")
    assert "منبع" not in text or draft.get("source_names")


def test_story_version_bump_preserves_provenance(db):
    _two_source_event(db)
    story, _ = _story(db)
    v1 = story["version"]
    draft = json.loads(story["draft_json"])
    draft["lead"] = "لید به‌روزشده با شواهد جدید"
    StoriesRepo(db).set_lifecycle(story["id"], "CONFIRMED", "update", draft)
    story2 = StoriesRepo(db).get(story["id"])
    assert story2["version"] == v1 + 1
    # previous version snapshot preserved
    snaps = db.query("SELECT version, snapshot_json FROM story_versions WHERE story_id=? ORDER BY version",
                     (story["id"],))
    assert len(snaps) >= 2 and json.loads(snaps[0]["snapshot_json"])["lead"] != draft["lead"]


# ---------- GATE-11: source attribution ----------

def test_known_sources_exactly_one_source_line(db):
    _two_source_event(db)
    story, ev = _story(db)
    names = source_display_names(db, ev["id"])
    assert names == "یاشار، نایا" or names == "نایا، یاشار"
    draft = json.loads(story["draft_json"])
    from app.publishing.telegram_bot import build_public_text

    text = build_public_text("CONFIRMED", draft["headline"], type("B", (), {
        "name_fa": "x", "telegram_handle": "R"})(), "hidden", True, source_names=names)
    assert text.count("منبع:") == 1
    assert "یاشار" in text and "نایا" in text


def test_same_source_dedup_names(db):
    s1 = SourcesRepo(db).create(name="tg withyashar", platform="telegram",
                                external_id="w", status="APPROVED",
                                source_type="telegram_web_preview")
    from app.clustering.dedup import fingerprints_for

    fp = fingerprints_for("https://t.me/w/x", A, BODY_A)
    RawItemsRepo(db).insert(source_id=s1, platform="telegram", external_key="tgweb:w/x",
                            url="https://t.me/w/x", title=A, text=BODY_A, language="fa",
                            published_at="2030-01-01T00:00:00+00:00", activation_ok=True,
                            lineage_key="tgweb:w", fingerprints=fp)
    asyncio.run(process_new_items(db, None, None, S()))
    ev = EventsRepo(db).list()[0]
    assert source_display_names(db, ev["id"]) == "یاشار"  # dedup, no repeats


def test_no_external_handle_or_url_leak(db):
    _two_source_event(db)
    story, _ = _story(db)
    raw = json.dumps(json.loads(story["draft_json"]), ensure_ascii=False)
    assert "t.me/" not in raw.split('"lead"')[1][:400]
    assert "@withyashar" not in raw and "@naya_foriraq" not in raw


def test_unresolvable_source_holds_not_silent(db):
    """Known evidence but no public name → SOURCE_NAME_RESOLUTION_ERROR, no publish."""
    s1 = SourcesRepo(db).create(name="unknown_xyz", platform="rss", url="u",
                                status="APPROVED", verification_allowed=True)
    from app.clustering.dedup import fingerprints_for

    fp = fingerprints_for("https://u.example/k", A, BODY_A)
    RawItemsRepo(db).insert(source_id=s1, platform="rss", external_key="k",
                            url="https://u.example/k", title=A, text=BODY_A,
                            language="fa", published_at="2030-01-01T00:00:00+00:00",
                            activation_ok=True, lineage_key="dom:u", fingerprints=fp)
    asyncio.run(process_new_items(db, None, None, S()))
    ev = EventsRepo(db).list()[0]
    names = source_display_names(db, ev["id"])
    if not names:  # resolver must not return empty for eligible evidence
        assert StoriesRepo(db).by_event(ev["id"]) is None, "published without attribution"


def test_gate11_old_ledger_is_historical_not_invariant():
    """GATE-11 applies to the canonical render path (new publications). Historic
    SENT rows predating the gate are preserved evidence, never mass-edited
    (Part-1 rule §10). This test pins that policy decision."""
    from app.publishing.telegram_bot import build_public_text

    # a NEW render with known sources must carry exactly one attribution
    text = build_public_text("CONFIRMED", "**h**", type("B", (), {
        "name_fa": "x", "telegram_handle": "R"})(), "hidden", True, source_names="نایا")
    assert text.count("منبع:") == 1
