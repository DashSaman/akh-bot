"""MASTER-FINAL — registry import + §24 identity-dedup automated rules."""
import json
from pathlib import Path

import pytest

from app.db.repo import RawItemsRepo, SourcesRepo
from app.newsroom.source_registry import (
    import_full_registry, role_of, speed_tier_of,
)
from app.newsroom.v2_pipeline import process_new_items_v2
from app.verification import evidence as ev

ROOT = Path(__file__).resolve().parent.parent
ENDPOINTS = json.loads((ROOT / "data" / "source_registry_endpoints.json")
                       .read_text(encoding="utf-8"))


def test_registry_artifact_scale():
    """Owner XLSX converted: 110 endpoints / 78 canonical identities."""
    assert len(ENDPOINTS) >= 100
    assert len({e["entity"].lower() for e in ENDPOINTS}) == 78


def test_role_semantics_mapping():
    assert role_of("Independent newsroom", "Yes", "Newsroom") == (
        "INDEPENDENT_NEWSROOM", True, True)
    assert role_of("Official statement", "No", "Government") == (
        "OFFICIAL_PRIMARY", False, False)
    assert role_of("Direct person", "No — direct person", "Person") == (
        "PERSON_STATEMENT", False, False)
    # newsroom mirror never counts as a second origin
    assert role_of("Newsroom mirror / alert", "No — same newsroom", "Mirror") == (
        "INDEPENDENT_NEWSROOM", False, False)
    # independent OSINT may corroborate; mirror OSINT may not
    assert role_of("Specialist OSINT", "Conditional", "OSINT")[2] is True
    assert role_of("Specialist OSINT", "No — same project", "OSINT")[2] is False


def test_speed_tiers():
    assert speed_tier_of("1–2 min")[0] == "FAST"
    assert speed_tier_of("realtime")[1] == 120
    assert speed_tier_of("5–15 min")[0] == "SLOW"
    assert speed_tier_of("2–5 min")[0] == "MID"
    assert speed_tier_of("1–2 min") == ("FAST", 120)
    assert speed_tier_of("event-driven")[0] == "EVENT"


def test_import_full_registry_idempotent(db):
    s1 = import_full_registry(db, ENDPOINTS)
    s2 = import_full_registry(db, ENDPOINTS)  # rerun: pure update, no dupes
    assert s1["created"] == 110
    assert s2["created"] == 0 and s2["updated"] == 110  # pure update on rerun
    n = db.query_one("SELECT COUNT(*) AS n FROM sources WHERE identity!=''")["n"]
    assert n == 110, "one sources row per endpoint"
    identities = db.query_one(
        "SELECT COUNT(DISTINCT identity) AS n FROM sources WHERE identity!=''")["n"]
    assert identities == 78
    # truthful endpoint states
    x_blocked = db.query_one(
        "SELECT COUNT(*) AS n FROM sources WHERE platform='x'"
        " AND endpoint_state='BLOCKED_AUTH'")["n"]
    assert x_blocked == 27
    tg_active = db.query_one(
        "SELECT COUNT(*) AS n FROM sources WHERE platform='telegram'"
        " AND endpoint_state='ACTIVE'")["n"]
    assert tg_active == 18
    # existing naya/yashar untouched
    assert db.query_one(
        "SELECT COUNT(*) AS n FROM sources WHERE identity='' AND source_control_state='OWNER_ENABLED'")["n"] == 0


# ---- §24 permanent dedup rules (live identity collapse) ----

def _wire(db, identity, name, url, platform="rss"):
    sid = SourcesRepo(db).create(name=name, platform=platform, url=url,
                                 status="APPROVED", verification_allowed=True)
    SourcesRepo(db).update(sid, identity=identity, source_control_state="OWNER_ENABLED")
    return sid


def _claim_with_evidence(db, sid, key, text):
    RawItemsRepo(db).insert(source_id=sid, platform="rss", external_key=key,
                            title="", text=text, activation_ok=True,
                            published_at="2026-10-03T10:00:00+00:00")
    class B: short_name = "راسته"; name_fa = "راسته"; tagline_fa = "خ"; telegram_handle = "R"
    class S: event_engine_v2_enabled = True; max_public_story_details = 5; edit_debounce_seconds = 120; verifying_deadline_minutes = 60; standard_max_age_minutes = 180
    process_new_items_v2(db, B(), S())
    return db.query_one("SELECT id FROM claims ORDER BY id DESC LIMIT 1")["id"]


def test_reuters_site_plus_social_one_origin(db):
    a = _wire(db, "Reuters", "Reuters (website)", "https://reuters.com/feed")
    b = _wire(db, "Reuters", "Reuters on X", "https://x.com/Reuters")
    cid = _claim_with_evidence(db, a, "r1", "دلار امروز در بازار آزاد به کانال تازه رسید")
    cid2 = _claim_with_evidence(db, b, "r2", "دلار امروز در بازار آزاد به کانال تازه رسید")
    origins = ev.independent_origins(db, cid)
    assert origins == ["identity:reuters"], origins


def test_ynet_three_endpoints_one_origin(db):
    ids = [_wire(db, "Ynet", f"Ynet {p}", u) for p, u in (
        ("web", "https://ynetnews.com/feed"), ("x", "https://x.com/ynetalerts"),
        ("tg", "https://t.me/ynetnews"))]
    cids = [_claim_with_evidence(db, s, f"y{i}",
            "بورس تهران امروز با رشد شاخص همراه بود") for i, s in enumerate(ids)]
    assert ev.independent_origins(db, cids[0]) == ["identity:ynet"]


def test_netanyahu_two_accounts_one_person_origin(db):
    ids = [_wire(db, "Netanyahu", f"Netanyahu {p}", u) for p, u in (
        ("x", "https://x.com/Netanyahu"), ("tg", "https://t.me/Netanyahu"))]
    cids = [_claim_with_evidence(db, s, f"n{i}",
            "قیمت طلا امروز در بازار افزایش یافت") for i, s in enumerate(ids)]
    assert ev.independent_origins(db, cids[0]) == ["identity:netanyahu"]


def test_hebrew_and_english_same_newsroom_one_origin(db):
    ids = [_wire(db, "Ynet", f"Ynet {lang}", url) for lang, url in (
        ("he", "https://ynetnews.com/he/feed"), ("en", "https://ynetnews.com/en/feed"))]
    cids = [_claim_with_evidence(db, s, f"h{i}",
            "شاخص بورس امروز رشد داشت و معاملات فعال شد") for i, s in enumerate(ids)]
    assert ev.independent_origins(db, cids[0]) == ["identity:ynet"]


def test_two_independent_newsrooms_two_origins_corroborated(db):
    a = _wire(db, "Reuters", "Reuters", "https://reuters.com/feed")
    b = _wire(db, "AP", "AP", "https://apnews.com/feed")
    cid = _claim_with_evidence(db, a, "i1", "دلار امروز در بازار آزاد به کانال تازه رسید")
    cid2 = _claim_with_evidence(db, b, "i2", "دلار امروز در بازار آزاد به کانال تازه رسید")
    assert set(ev.independent_origins(db, cid)) == {"identity:reuters", "identity:ap"}
    assert db.query_one("SELECT state FROM claims WHERE id=?", (cid,))["state"] == "CORROBORATED"


def test_two_osint_datasets_corroborate_not_duplicate_stories(db):
    a = _wire(db, "NetBlocks", "NetBlocks", "https://netblocks.org/feed")
    b = _wire(db, "OONI", "OONI", "https://ooni.org/feed")
    cid = _claim_with_evidence(db, a, "o1",
        "گزارش‌هایی درباره اختلال اینترنت در سراسر کشور امروز منتشر شد")
    cid2 = _claim_with_evidence(db, b, "o2",
        "گزارش‌هایی درباره اختلال اینترنت در سراسر کشور امروز منتشر شد")
    events = db.query_one("SELECT COUNT(*) AS n FROM events")["n"]
    assert events == 1, "OSINT datasets attach to the SAME event — no duplicate story"
    stories = db.query_one("SELECT COUNT(*) AS n FROM stories")["n"]
    assert stories <= 1
