"""PART-4 — verification lifecycle: EvidenceLink (CORE-007), VerificationRun
(CORE-008), independent-origin semantics, contradiction trace, reverify
cadence, 60-minute deadline, admin trace view.

Fixtures per Part-4 spec §12.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.db.repo import PublicationsRepo, RawItemsRepo, SourcesRepo, utcnow
from app.jobs.runner import make_send_handler
from app.newsroom.v2_pipeline import process_new_items_v2
from app.verification import evidence as ev
from app.verification import runs as vr

T0 = "2026-10-03T10:00:00+00:00"


class Brand:
    short_name = "راسته"; name_fa = "راسته"; tagline_fa = "خبر و راستی‌آزمایی"
    telegram_handle = "RastehNews"


class S:
    event_engine_v2_enabled = True
    max_public_story_details = 5
    edit_debounce_seconds = 120
    verifying_deadline_minutes = 60
    standard_max_age_minutes = 180


def _ts(minutes: int) -> str:
    return (datetime.fromisoformat(T0) + timedelta(minutes=minutes)).isoformat()


def _source(db, name, **kw):
    sid = SourcesRepo(db).create(name=name, platform="telegram", url=f"t.me/{name}",
                                 status="APPROVED", **kw)
    SourcesRepo(db).update(sid, source_control_state="OWNER_ENABLED")
    return sid


def _item(db, source_id, key, text, minutes=0, lineage_key=""):
    return RawItemsRepo(db).insert(
        source_id=source_id, platform="telegram", external_key=key, title="",
        text=text, published_at=_ts(minutes), activation_ok=True,
        lineage_key=lineage_key)


def _settings(settings):
    return settings.model_copy(update={"event_engine_v2_enabled": True})


# ---- §12: 1 source → SINGLE_SOURCE where required (high-risk) ----

def test_high_risk_single_origin_stays_single_source(db, settings):
    s = _settings(settings)
    a = _source(db, "reuters_x", verification_allowed=True)
    _item(db, a, "h1", "در حمله موشکی به پایگاه آمریکایی در عراق ۵ نظامی کشته شدند", 0)
    process_new_items_v2(db, Brand(), s)
    claims = db.query("SELECT * FROM claims")
    assert len(claims) == 1
    assert claims[0]["risk_level"] == "high"
    # single independent origin + high risk → SINGLE_SOURCE, never CONFIRMED
    assert claims[0]["state"] == "SINGLE_SOURCE"
    cid = claims[0]["id"]
    assert ev.independent_origin_count(db, cid) == 1
    runs = vr.runs_for_claim(db, cid)
    assert runs and runs[0]["trigger"] == "NEW_EVIDENCE"
    assert runs[0]["high_risk"] == 1


def test_high_risk_single_source_never_becomes_definitive(db, settings):
    """§8 regression: even repeated same-origin reposts must not confirm."""
    s = _settings(settings)
    a = _source(db, "solo_agency")
    _item(db, a, "r1", "پلیس اعلام کرد ۳ نفر در بازداشت دستگیر شدند", 0, lineage_key="agency_origin")
    _item(db, a, "r2", "پلیس اعلام کرد ۳ نفر در بازداشت دستگیر شدند", 2, lineage_key="agency_origin")
    process_new_items_v2(db, Brand(), s)
    claims = db.query("SELECT * FROM claims")
    assert len(claims) == 1
    assert claims[0]["state"] in ("SINGLE_SOURCE", "UNVERIFIED")
    assert claims[0]["state"] != "CONFIRMED"


# ---- §12: 2 independent sources → CORROBORATED ----

def test_two_independent_origins_corroborated(db, settings):
    s = _settings(settings)
    a = _source(db, "reuters", verification_allowed=True)
    b = _source(db, "associated_press", verification_allowed=True)
    _item(db, a, "i1", "قیمت دلار در بازار آزاد تهران امروز به کانال جدید رسید", 0)
    _item(db, b, "i2", "قیمت دلار در بازار آزاد تهران امروز به کانال جدید رسید", 3)
    process_new_items_v2(db, Brand(), s)
    claims = db.query("SELECT * FROM claims")
    assert len(claims) == 1, "same factual claim across independent wires = ONE claim"
    cid = claims[0]["id"]
    origins = ev.independent_origins(db, cid)
    assert len(origins) == 2
    assert claims[0]["state"] == "CORROBORATED"
    links = db.query("SELECT * FROM evidence_links WHERE claim_id=?", (cid,))
    assert len(links) == 2  # provenance preserved per item


# ---- §12: same identity through 2 endpoints → 1 independent origin ----

def test_same_identity_two_endpoints_one_origin(db, settings):
    """CENTCOM EN + CENTCOM AR are ONE institutional origin (registry identity)."""
    s = _settings(settings)
    en = _source(db, "CENTCOM EN")
    ar = _source(db, "CENTCOM AR")
    _item(db, en, "c1", "نیروهای ما مواضع تهاجمی را در بغداد هدف قرار دادند", 0)
    _item(db, ar, "c2", "نیروهای ما مواضع تهاجمی را در بغداد هدف قرار دادند", 2)
    process_new_items_v2(db, Brand(), s)
    claims = db.query("SELECT * FROM claims")
    cid = claims[0]["id"]
    origins = ev.independent_origins(db, cid)
    assert len(origins) == 1, f"identity collapse broken: {origins}"
    assert claims[0]["state"] != "CORROBORATED"


# ---- §12: forward/repost → not independent ----

def test_forward_repost_not_independent(db, settings):
    s = _settings(settings)
    a = _source(db, "wire_a")
    b = _source(db, "reposter_b")
    text = "بانک مرکزی نرخ بهره را در نشست امروز تغییر داد"
    _item(db, a, "f1", text, 0, lineage_key="origin:reuters")
    _item(db, b, "f2", text, 4, lineage_key="origin:reuters")  # forwarded copy
    process_new_items_v2(db, Brand(), s)
    claims = db.query("SELECT * FROM claims")
    cid = claims[0]["id"]
    assert len(ev.independent_origins(db, cid)) == 1
    assert claims[0]["state"] != "CORROBORATED"


# ---- §12: official statement semantics preserved ----

def test_official_statement_authoritative_only_for_attribution(db, settings):
    """An OFFICIAL_PRIMARY origin supports «X announced Y» but never counts as
    an independent newsroom confirmation of the underlying fact."""
    s = _settings(settings)
    off = _source(db, "centcom en", source_role="OFFICIAL_PRIMARY",
                  verification_allowed=False)
    _item(db, off, "o1", "نیروهای ما حمله موشکی امروز به پایگاه را تأیید کردند", 0)
    process_new_items_v2(db, Brand(), s)
    claims = db.query("SELECT * FROM claims")
    cid = claims[0]["id"]
    assert ev.is_official_origin(db, cid) is True
    assert ev.independent_origin_count(db, cid) == 1
    # official alone: high-risk attack claim must stay non-definitive
    assert claims[0]["state"] in ("SINGLE_SOURCE", "UNVERIFIED", "CONFLICTING")
    assert claims[0]["state"] != "CONFIRMED"


# ---- §12: contradicting number/negation → CONFLICTING trace ----

def test_contradiction_creates_traceable_conflict(db, settings):
    s = _settings(settings)
    a = _source(db, "naya_like", verification_allowed=True)
    b = _source(db, "yashar_like", verification_allowed=True)
    _item(db, a, "x1", "در حمله موشکی امروز به پایگاه ۱۰ نظامی کشته شدند", 0)
    process_new_items_v2(db, Brand(), s)
    _item(db, b, "x2", "در حمله موشکی امروز به پایگاه ۱۵ نظامی کشته شدند", 5)
    process_new_items_v2(db, Brand(), s)
    claims = db.query("SELECT * FROM claims ORDER BY id")
    assert len(claims) == 2, "both contradicting claims preserved"
    contra_runs = db.query(
        "SELECT * FROM verification_runs WHERE trigger=:t", {"t": vr.CONTRADICTION})
    assert contra_runs, "CONTRADICTION VerificationRun required"
    run = contra_runs[0]
    assert run["contradiction_count"] >= 1
    assert run["result"] in ("CONFLICTING", "SINGLE_SOURCE", "UNVERIFIED")
    # at least one claim carries CONTRADICTS evidence link
    contra_links = db.query(
        "SELECT * FROM evidence_links WHERE relation=:r", {"r": ev.CONTRADICTS})
    assert contra_links
    # no fabricated resolution: neither claim auto-CONFIRMED
    assert all(c["state"] != "CONFIRMED" for c in claims)


# ---- §12: EvidenceLink provenance preserved ----

def test_evidence_link_provenance_preserved(db, settings):
    s = _settings(settings)
    a = _source(db, "prov_src", verification_allowed=True)
    rid = _item(db, a, "p1", "وزیر نفت گفت تولید نفت کشور امروز افزایش یافت", 0,
                lineage_key="origin:ministry")
    process_new_items_v2(db, Brand(), s)
    link = db.query_one("SELECT * FROM evidence_links")
    assert link["raw_item_id"] == rid
    assert link["source_id"] == a
    assert link["lineage_key"] == "origin:ministry"
    assert link["relation"] == ev.SUPPORTS
    assert link["observed_at"], "observed_at recorded"


# ---- §12: scheduled reverify → VerificationRun (no duplicates per slot) ----

def test_scheduled_reverify_single_run_per_slot(db, settings):
    s = _settings(settings)
    a = _source(db, "held_src")
    _item(db, a, "v1", "گزارش‌هایی درباره حمله هوایی به پایگاه منتشر شد", 0)
    process_new_items_v2(db, Brand(), s)   # pass 1 (creates + maybe holds)
    process_new_items_v2(db, Brand(), s)   # pass 2 same 5-min slot
    process_new_items_v2(db, Brand(), s)   # pass 3 same slot
    sched = db.query(
        "SELECT * FROM verification_runs WHERE trigger=:t", {"t": vr.SCHEDULED_REVERIFY})
    per_event = {}
    for r in sched:
        per_event[r["event_id"]] = per_event.get(r["event_id"], 0) + 1
    assert all(v == 1 for v in per_event.values()), \
        f"duplicate scheduled runs in one slot: {per_event}"
    assert sched, "scheduled reverify must run for unresolved events"


def test_scheduled_reverify_next_verify_at_set(db, settings):
    s = _settings(settings)
    a = _source(db, "unres_src")
    _item(db, a, "u1", "ادعایی درباره حمله پهپادی در منطقه مرزی منتشر شد", 0)
    process_new_items_v2(db, Brand(), s)
    row = db.query_one(
        "SELECT next_verify_at AS nv FROM claims ORDER BY id DESC LIMIT 1")
    assert row and row["nv"], "unresolved claims need next_verify_at"
    ev_row = db.query_one(
        "SELECT next_verify_at AS nv FROM verification_runs ORDER BY id DESC LIMIT 1")
    assert ev_row and ev_row["nv"]


# ---- §12: new evidence → new verification run ----

def test_new_evidence_new_run(db, settings):
    s = _settings(settings)
    a = _source(db, "evid_src", verification_allowed=True)
    _item(db, a, "e1", "دلار امروز در بازار آزاد به کانال تازه رسید", 0)
    process_new_items_v2(db, Brand(), s)
    n1 = db.query_one("SELECT COUNT(*) AS n FROM verification_runs")["n"]
    assert n1 >= 1
    b = _source(db, "evid_src2", verification_allowed=True)
    _item(db, b, "e2", "دلار امروز در بازار آزاد به کانال تازه رسید", 6)
    process_new_items_v2(db, Brand(), s)
    n2 = db.query_one("SELECT COUNT(*) AS n FROM verification_runs")["n"]
    assert n2 > n1, "new evidence must produce a new run"


# ---- §12: replay/idempotency — no duplicate links/runs ----

def test_replay_idempotent_no_duplicates(db, settings):
    s = _settings(settings)
    a = _source(db, "rep_src", verification_allowed=True)
    _item(db, a, "y1", "بورس تهران امروز با رشد شاخص همراه بود", 0)
    process_new_items_v2(db, Brand(), s)
    links1 = db.query_one("SELECT COUNT(*) AS n FROM evidence_links")["n"]
    runs1 = db.query_one("SELECT COUNT(*) AS n FROM verification_runs")["n"]
    process_new_items_v2(db, Brand(), s)  # full replay pass
    links2 = db.query_one("SELECT COUNT(*) AS n FROM evidence_links")["n"]
    runs2 = db.query_one("SELECT COUNT(*) AS n FROM verification_runs")["n"]
    assert links2 == links1, "replay must not duplicate evidence links"
    assert runs2 == runs1, "replay must not duplicate runs (same slot, deduped)"


# ---- §12: 60-minute deadline recorded ----

def test_sixty_minute_deadline_recorded(db, settings):
    s = settings.model_copy(update={
        "event_engine_v2_enabled": True, "verifying_deadline_minutes": 60})
    a = _source(db, "dl_src")
    _item(db, a, "d1", "گزارش‌هایی از انفجار در پایگاه نظامی امروز منتشر شد", 0)
    process_new_items_v2(db, Brand(), s)
    ev_row = db.query_one("SELECT * FROM events ORDER BY id DESC LIMIT 1")
    story_id = db.execute(
        "INSERT INTO stories(event_id,slug,headline,lead,draft_json,version,status,"
        " lifecycle,created_at,updated_at) VALUES(?,?,?,?,?,1,'PUBLISHED','PROVISIONAL',?,?)",
        (ev_row["id"], "deadline-test", "t", "t", "{}",
         _ts(-120), _ts(-120))).lastrowid
    process_new_items_v2(db, Brand(), s)
    dead = db.query(
        "SELECT * FROM verification_runs WHERE trigger=:t", {"t": vr.DEADLINE})
    assert dead, "DEADLINE VerificationRun required at 60-min resolution"
    assert any("DEADLINE_60MIN" in (r["reason_codes"] or "") for r in dead)
    story = db.query_one("SELECT lifecycle FROM stories WHERE id=?", (story_id,))
    assert story["lifecycle"] == "ARCHIVED"


# ---- admin trace view renders (smoke, auth-gated) ----

def test_admin_verification_trace_view(admin_client, settings):
    db = admin_client.app.state.db  # the app's own DB (FakeDb at akhbot.db)
    a = _source(db, "adm_src", verification_allowed=True)
    _item(db, a, "a1", "شاخص بورس امروز رشد داشت و معاملات فعال شد", 0)
    process_new_items_v2(db, Brand(), S())
    ev_row = db.query_one("SELECT * FROM events ORDER BY id DESC LIMIT 1")
    resp = admin_client.get(f"/admin/verification/{ev_row['id']}")
    assert resp.status_code == 200
    assert "ردیابی راستی‌آزمایی" in resp.text
    assert "NEW_EVIDENCE" in resp.text or "SCHEDULED_REVERIFY" in resp.text
    assert str(ev_row["id"]) in resp.text


def test_admin_verification_trace_requires_login(client, db):
    resp = client.get("/admin/verification/1", follow_redirects=False)
    assert resp.status_code in (303, 401)
