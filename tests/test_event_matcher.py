"""P3-B — bounded candidate retrieval (no all-history scans) + event_matcher tests."""
from __future__ import annotations

import json
import re

from app.db.repo import utcnow

from app.newsroom.event_fingerprint import (
    EventFingerprint, decide, detect_event_type, detect_second_occurrence,
    extract_fingerprint,
)


def _fp(text, actor=None, at=None, occ=None, etype=None, loc=None):
    fp = extract_fingerprint(text, actor=actor, occurred_at=at,
                             explicit_occurrence_id=occ)
    if etype:
        fp.event_type = etype
    if loc:
        fp.location = loc.lower()
    return fp


def _cands(*pairs):
    return [(eid, fp) for eid, fp in pairs]


def _candidates_from_db(db, fp: EventFingerprint, limit: int = 12) -> list[tuple[int, EventFingerprint]]:
    """Bounded candidate retrieval mirroring production matcher: OPEN/recent events,
    same event_type or same actor tokens, continuation window, occurrence id.
    Deterministic; never all-history."""
    rows = db.query(
        "SELECT id, fingerprint_json, state FROM events"
        " WHERE state IN ('OPEN','PUBLISHED','HELD')"
        " ORDER BY last_seen_at DESC LIMIT ?", (limit,))
    out = []
    for r in rows:
        try:
            d = json.loads(r["fingerprint_json"] or "{}")
        except Exception:
            continue
        out.append((r["id"], EventFingerprint(
            primary_actors=d.get("primary_actors", []),
            predicate_tokens=set(d.get("predicate_tokens", [])),
            object_tokens=set(d.get("object_tokens", [])),
            location=d.get("location"), event_type=d.get("event_type", "GENERAL_NEWS"),
            topic=d.get("topic", ""), conversation_context_ref=d.get("conversation_context_ref"),
            explicit_occurrence_id=d.get("explicit_occurrence_id"),
            occurred_at=d.get("occurred_at"), second_occurrence=d.get("second_occurrence", False))))
    return out


# ---- §15 negative: same actor+topic, different action → CREATE_NEW ----

def test_same_actor_same_topic_different_action_creates_new():
    fp1 = _fp("ترامپ درباره احتمال توافق با ایران در مصاحبه تایم صحبت می‌کند",
              actor="ترامپ", at="2030-01-01T10:00:00+00:00")
    fp2 = _fp("ترامپ اعلام می‌کند تحریم‌های جدید علیه ایران اعمال می‌شود",
              actor="ترامپ", at="2030-01-01T11:30:00+00:00")
    d2 = decide(fp2, _cands((1, fp1)), fp_ts=fp2.occurred_at)
    assert d2.decision in ("CREATE_NEW", "AMBIGUOUS_EVENT")


# ---- §16 positive: same event, different wording → ATTACH ----

def test_same_event_different_wording_attaches():
    fp1 = _fp("حمله پهپادی به پایگاه آمریکا در عراق انجام شد",
              at="2030-01-01T10:00:00+00:00", etype="MILITARY_STRIKE", loc="عراق")
    fp2 = _fp("پهپادهایی پایگاه آمریکایی در خاک عراق را هدف قرار دادند",
              at="2030-01-01T10:20:00+00:00", etype="MILITARY_STRIKE", loc="عراق")
    d = decide(fp2, _cands((1, fp1)), fp_ts=fp1.occurred_at)
    assert d.decision == "ATTACH_EXISTING" and d.candidate_event_id == 1


# ---- §19 negative: two strikes, different locations → CREATE_NEW ----

def test_two_strikes_different_locations_create_new():
    fp1 = _fp("حمله موشکی به پایگاه در عراق", at="2030-01-01T10:00:00+00:00",
              etype="MILITARY_STRIKE", loc="عراق")
    fp2 = _fp("حمله موشکی به پایگاه در سوریه", at="2030-01-01T13:00:00+00:00",
              etype="MILITARY_STRIKE", loc="سوریه")
    d = decide(fp2, _cands((1, fp1)), fp_ts=fp1.occurred_at)
    assert d.decision == "CREATE_NEW" and "LOCATION_CONFLICT" in d.reason_codes


# ---- §21 negative: interview vs separate announcement → different events ----

def test_interview_vs_sanctions_announcement_separate():
    i1 = _fp("ترامپ در مصاحبه تایم درباره ایران صحبت کرد", actor="ترامپ",
             at="2030-01-01T10:00:00+00:00", etype="INTERVIEW",
             occ="TIME-interview-trump")
    a1 = _fp("ترامپ اعلام کرد تحریم‌های جدید اعمال می‌شود", actor="ترامپ",
             at="2030-01-01T11:30:00+00:00", etype="POLITICAL_ANNOUNCEMENT")
    d = decide(a1, _cands((1, i1)), fp_ts=a1.occurred_at)
    assert d.decision == "CREATE_NEW"


# ---- §20 positive: developing incident casualty update attaches ----

def test_developing_incident_update_attaches():
    fp1 = _fp("انفجاری در مرکز بغداد رخ داد", at="2030-01-01T10:00:00+00:00",
              etype="LIVE_INCIDENT", loc="بغداد")
    fp2 = _fp("شماره تلفات انفجار مرکز بغداد افزایش یافت", at="2030-01-01T10:20:00+00:00",
              etype="LIVE_INCIDENT", loc="بغداد")
    d = decide(fp2, _cands((1, fp1)), fp_ts=fp1.occurred_at)
    assert d.decision == "ATTACH_EXISTING"


# ---- explicit second-occurrence marker → CREATE_NEW ----

def test_second_strike_marker_creates_new():
    fp1 = _fp("حمله موشکی به پایگاه در عراق", at="2030-01-01T10:00:00+00:00",
              etype="MILITARY_STRIKE", loc="عراق")
    fp2 = _fp("حمله دوم موشکی به پایگاه در عراق", at="2030-01-01T10:30:00+00:00",
              etype="MILITARY_STRIKE", loc="عراق")
    d = decide(fp2, _cands((1, fp1)), fp_ts=fp1.occurred_at)
    assert d.decision == "CREATE_NEW"


# ---- cross-source same event → attach (source id not identity) ----

def test_cross_source_same_event_attaches():
    fp1 = _fp("تحریم‌های جدید آمریکا علیه ایران اعلام شد", actor="آمریکا",
              at="2030-01-01T09:00:00+00:00", etype="POLITICAL_ANNOUNCEMENT")
    fp2 = _fp("واشنگتن تحریم‌های تازه‌ای را علیه ایران اعلام کرد", actor="آمریکا",
              at="2030-01-01T09:10:00+00:00", etype="POLITICAL_ANNOUNCEMENT")
    d = decide(fp2, _cands((7, fp1)), fp_ts=fp1.occurred_at)
    assert d.decision in ("ATTACH_EXISTING", "AMBIGUOUS_EVENT")


# ---- incomplete/context-only items are NOT event-eligible (REG-031 guard) ----

def test_context_only_not_event_eligible():
    from app.newsroom import claim_completeness as cc

    frag = "ترامپ به مجله تایم:"
    r = cc.evaluate(frag)
    assert r.state == "CONTEXT_ONLY" and r.publishable is False
    fp = extract_fingerprint(frag, occurred_at="2030-01-01T10:00:00+00:00")
    # guard: matcher consumers must skip non-publishable items — fingerprint of a
    # bare prefix carries no predicate/object and must not attach to anything
    probe = _fp("ترامپ در مصاحبه تایم درباره ایران صحبت کرد", actor="ترامپ",
                at="2030-01-01T10:05:00+00:00", etype="INTERVIEW")
    d = decide(fp, _cands((1, probe)), fp_ts=fp.occurred_at)
    assert d.decision == "CREATE_NEW"  # cannot contaminate a real event


# ---- deterministic repeated decision (§43) ----

def test_deterministic_repeated_decision():
    fp = _fp("حمله موشکی به پایگاه در عراق", at="2030-01-01T10:00:00+00:00",
             etype="MILITARY_STRIKE", loc="عراق")
    cand = _fp("حمله موشکی به پایگاه در عراق", at="2030-01-01T10:10:00+00:00",
               etype="MILITARY_STRIKE", loc="عراق")
    cands = _cands((1, cand))
    results = {decide(fp, cands, fp_ts=fp.occurred_at).decision for _ in range(5)}
    assert results == {"ATTACH_EXISTING"}


# ---- second-occurrence + event-type detectors ----

def test_second_occurrence_and_type_detectors():
    assert detect_second_occurrence("حمله دوم موشکی انجام شد")
    assert not detect_second_occurrence("حمله موشکی انجام شد")
    assert detect_event_type("حمله موشکی به پایگاه") == "MILITARY_STRIKE"
    assert detect_event_type("اختلال اینترنت در تهران") == "INTERNET_OUTAGE"
    assert detect_event_type("گزارش معمولی روز") == "GENERAL_NEWS"
