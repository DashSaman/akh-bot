"""Directive 2026-10-04 — full-source coverage + source diversity regressions.

Soft anti-monopoly: canonical-identity share caps defer a story ONLY when
alternatives exist; breaking news never deferred; priority is ORDER-only and
never trust; same-identity endpoints count once; watchdog detects monopoly
and starvation without ever blocking publication.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.newsroom.diversity import (
    defer_for_diversity, diversity_metrics, story_source_identities)
from app.verification.gates import classify_priority, decide_claim_state, priority_tier

_now = datetime.now(timezone.utc)
_TS = "2030-01-01T00:00:00+00:00"


def _src(db, name, ident, breaking=0):
    db.execute(
        "INSERT INTO sources (name, platform, external_id, url, language, category,"
        " source_type, status, enabled, priority, notes, created_at, identity,"
        " breaking_source)"
        " VALUES (?, 'telegram', ?, ?, '', '', 'direct', 'APPROVED', 1, 50, '',"
        " ?, ?, ?)",
        (name, ident, "https://t.me/" + name, _TS, ident, breaking))
    return db.query_one("SELECT id FROM sources WHERE name=?", (name,))["id"]


def _item(db, sid, tag="x"):
    db.execute(
        "INSERT INTO raw_items (source_id, platform, external_key, url, title, text,"
        " language, fetched_at, activation_ok, processed_state)"
        " VALUES (?, 'telegram', ?, '', ?, '', 'fa', ?, 1, 'PROCESSED')",
        (sid, "k" + tag + str(sid), tag, _TS))
    return db.query_one("SELECT MAX(id) id FROM raw_items")["id"]


def _event(db, item_ids, title="e"):
    db.execute(
        "INSERT INTO events (title, status, verification, independent_count,"
        " first_seen_at, last_seen_at)"
        " VALUES (?, 'NEW', 'UNVERIFIED', 1, ?, ?)", (title, _TS, _TS))
    eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
    for iid in item_ids:
        db.execute("INSERT INTO event_items (event_id, raw_item_id) VALUES (?, ?)",
                   (eid, iid))
    return eid


def _sent_story(db, eid, slug):
    db.execute(
        "INSERT INTO stories (event_id, slug, headline, lead, draft_json, version,"
        " status, created_at, updated_at) VALUES (?, ?, 'خبر سرنوشت‌ساز', 'لید', '{}',"
        " 1, 'PUBLISHED', ?, ?)", (eid, slug, _TS, _TS))
    sid = db.query_one("SELECT MAX(id) id FROM stories")["id"]
    db.execute(
        "INSERT INTO publications (story_id, platform, payload_hash, attempt, status,"
        " created_at, updated_at) VALUES (?, 'telegram', ?, 1, 'SENT', ?, ?)",
        (sid, "h" + slug, _now.isoformat(timespec="seconds"),
         _now.isoformat(timespec="seconds")))
    return sid


def test_same_identity_endpoints_count_once(db):
    a = _src(db, "reuters_a", "Reuters")
    b = _src(db, "reuters_b", "Reuters")  # second endpoint, SAME entity
    eid = _event(db, [_item(db, a, "ra"), _item(db, b, "rb")])
    assert story_source_identities(db, eid) == {"Reuters"}


def test_defer_only_with_alternatives_and_over_share(db):
    naya = _src(db, "tg_naya", "NAYA")
    other = _src(db, "tg_other", "OtherCorp")
    # 6 posts from NAYA in the window, 2 from others -> NAYA dominates
    for i in range(6):
        eid = _event(db, [_item(db, naya, "n%d" % i)], "naya%d" % i)
        _sent_story(db, eid, "slug-n%d" % i)
    for i in range(2):
        eid = _event(db, [_item(db, other, "o%d" % i)], "oth%d" % i)
        _sent_story(db, eid, "slug-o%d" % i)
    fresh = _event(db, [_item(db, naya, "fresh")], "nayaFresh")
    # no alternatives -> publish (anti-monopoly must not censor the only voice)
    assert defer_for_diversity(db, fresh, 50, alternatives_ready=0) is False
    # alternatives exist -> deferred this pass, retried next pass
    assert defer_for_diversity(db, fresh, 50, alternatives_ready=3) is True
    # a different identity's story passes untouched
    other_ev = _event(db, [_item(db, other, "o9")], "oth9")
    assert defer_for_diversity(db, other_ev, 50, alternatives_ready=3) is False


def test_breaking_news_never_deferred(db):
    naya = _src(db, "tg_naya2", "NAYA2")
    for i in range(6):
        eid = _event(db, [_item(db, naya, "b%d" % i)], "brk%d" % i)
        _sent_story(db, eid, "slug-b%d" % i)
    ev = _event(db, [_item(db, naya, "war")], "war")
    # P0 breaking weight (war/internet/currency) always passes
    assert defer_for_diversity(db, ev, 95, alternatives_ready=5) is False
    # breaking-flagged source always passes even at low weight
    bsrc = _src(db, "tg_break", "BreakFeed", breaking=1)
    ev2 = _event(db, [_item(db, bsrc, "low")], "low")
    assert defer_for_diversity(db, ev2, 30, alternatives_ready=5) is False


def test_small_sample_never_deferred(db):
    a = _src(db, "one", "One")
    for i in range(2):  # below MIN_SAMPLE
        eid = _event(db, [_item(db, a, "s%d" % i)], "sm%d" % i)
        _sent_story(db, eid, "slug-s%d" % i)
    ev = _event(db, [_item(db, a, "s9")], "sm9")
    assert defer_for_diversity(db, ev, 50, alternatives_ready=3) is False


def test_priority_is_order_only_never_trust(db):
    # speed/priority of NAYA-Yashar never changes claim verification
    assert decide_claim_state("حمله موشکی با ۱۰ کشته", independent_sources=1,
                              has_contradiction=False, risk="high") == "SINGLE_SOURCE"
    assert decide_claim_state("بازدید نمایشگاه کتاب", independent_sources=1,
                              has_contradiction=False, risk="low") == "UNVERIFIED"
    assert decide_claim_state("اعلام رسمی وزارت خارجه", independent_sources=2,
                              has_contradiction=False, risk="high") == "CORROBORATED"


def test_iran_p0_beats_unrelated_p3(db):
    t0, w0 = classify_priority("حمله موشکی به ایران و قطعی اینترنت در تهران")
    t3, w3 = classify_priority("نتایج لیگ فوتبال باشگاهی شب گذشته")
    assert priority_tier(w0) == "P0" and w0 >= 88
    assert priority_tier(w3) == "P3" and w3 < 60
    assert w0 > w3


def test_metrics_shape(db):
    a = _src(db, "mx", "MxIdentity")
    for i in range(3):
        eid = _event(db, [_item(db, a, "m%d" % i)], "mx%d" % i)
        _sent_story(db, eid, "slug-m%d" % i)
    m = diversity_metrics(db, hours=1)
    assert m["total_new_posts"] == 3 and m["unique_identities"] == 1
    assert m["top"][0]["identity"] == "MxIdentity"


def test_watchdog_monopoly_and_starvation(db):
    from app.ingestion.scheduler import _diversity_and_starvation_check
    from app.db.repo import SettingsRepo
    dom = _src(db, "dom", "Dominant")
    for i in range(8):
        eid = _event(db, [_item(db, dom, "d%d" % i)], "dom%d" % i)
        _sent_story(db, eid, "slug-d%d" % i)
    # 6 waiting identities with never-sent stories
    for i in range(6):
        o = _src(db, "w%d" % i, "Wait%d" % i)
        eid = _event(db, [_item(db, o, "w%d" % i)], "wait%d" % i)
        db.execute(
            "INSERT INTO stories (event_id, slug, headline, lead, draft_json, version,"
            " status, created_at, updated_at) VALUES (?, ?, 'خبر', 'لید', '{}', 1,"
            " 'DRAFT', ?, ?)", (eid, "wslug%d" % eid, _TS, _TS))
    _diversity_and_starvation_check(db)
    mono = SettingsRepo(db).get("SOURCE_MONOPOLY_DETECTED")
    assert mono and "Dominant" in mono, "monopoly must be detected (warn-only)"
    # starvation: 5 fresh eligible items never linked to any event
    st = _src(db, "starved", "StarvedFeed")
    now2 = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for i in range(5):
        db.execute(
            "INSERT INTO raw_items (source_id, platform, external_key, url, title,"
            " text, language, fetched_at, activation_ok, processed_state)"
            " VALUES (?, 'telegram', ?, '', 'خبر مهم بی‌پوشش', '', 'fa', ?, 1,"
            " 'PROCESSED')", (st, "z%d" % i, now2))
    _diversity_and_starvation_check(db)
    starve = SettingsRepo(db).get("SOURCE_STARVATION")
    assert starve and "StarvedFeed" in starve, "starvation must be detected"
