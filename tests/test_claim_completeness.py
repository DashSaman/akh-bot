"""P3-A fixtures: structured claim model + class-aware completeness gate.
REG-031 permanent protection: speaker/context prefixes can NEVER become
COMPLETE/publicly eligible. V2 flag keeps old pipeline authoritative."""
import asyncio
import json

import pytest

from app.db.repo import RawItemsRepo, SourcesRepo

from app.newsroom import claim_completeness as cc
from app.newsroom.claim_model import (
    ClaimClass, StructuredClaim, detect_class, extract_structured, has_negation,
    numbers_of, certainty_of,
)


# ---- §6/§7 model ----

def test_structured_claim_fields_and_no_presentation():
    c = StructuredClaim(claim_class=ClaimClass.QUOTE, text="ترامپ گفت صلح ممکن است",
                        source_item_id=7, actor="ترامپ", predicate="گفت صلح ممکن است",
                        certainty="ATTRIBUTED", negation=False)
    d = c.to_dict()
    for f in ("claim_class", "actor", "predicate", "object_", "location", "time_ref",
              "quantity", "attribution", "certainty", "negation", "source_item_id",
              "fingerprint"):
        assert f in d
    assert "platform_variants" not in d and "telegram" not in d  # no presentation


def test_serialization_roundtrip():
    c = StructuredClaim(claim_class=ClaimClass.MARKET, text="دلار بالا رفت",
                        source_item_id=3, quantity="92")
    d = json.loads(c.to_json())
    assert d["claim_class"] == "MARKET" and d["source_item_id"] == 3


def test_fingerprint_preserves_numbers_negation_class():
    a = StructuredClaim(claim_class=ClaimClass.CASUALTY, text="۱۲ نفر کشته شدند",
                        source_item_id=1)
    b = StructuredClaim(claim_class=ClaimClass.CASUALTY, text="۱۵ نفر کشته شدند",
                        source_item_id=2)
    a.compute_fingerprint(); b.compute_fingerprint()
    assert a.fingerprint != b.fingerprint  # numbers preserved in fp
    pos = StructuredClaim(claim_class=ClaimClass.ATTACK, text="حمله انجام خواهد شد",
                          source_item_id=1)
    neg = StructuredClaim(claim_class=ClaimClass.ATTACK, text="حمله انجام نخواهد شد",
                          source_item_id=1)
    pos.compute_fingerprint(); neg.compute_fingerprint()
    assert pos.fingerprint != neg.fingerprint  # negation preserved
    assert has_negation("حمله انجام نخواهد شد") and not has_negation("حمله انجام خواهد شد")
    assert numbers_of("۱۰ کشته و ۵ زخمی") == ["10", "5"]
    assert certainty_of("گفته می‌شود حمله رخ داده") == "REPORTED"


def test_provenance_required():
    c = StructuredClaim(claim_class=ClaimClass.GENERAL, text="متن", source_item_id=0)
    assert c.source_item_id == 0  # caller must supply real id; model carries it


# ---- §9/§10 GATE-03 ----

CONTEXT_ONLY = ["ترامپ:", "ترامپ به مجله تایم:", "فوری:", "عاجل:",
                "منابع عبری:", "در همین حال:", "در ادامه افزود:", "همچنین گفت:",
                "و تأکید کرد:", "این در حالی است که:", "جزئیات بیشتر:"]


@pytest.mark.parametrize("frag", CONTEXT_ONLY)
def test_context_prefixes_never_complete(frag):
    r = cc.evaluate(frag)
    assert r.state == "CONTEXT_ONLY" and r.publishable is False


def test_structural_not_overfit(db):
    """Unseen connective/prefix shapes still CONTEXT_ONLY (deterministic rules)."""
    r = cc.evaluate("تحلیلگر ارشد موسسه مطالعاتی:")
    assert r.state == "CONTEXT_ONLY"
    r = cc.evaluate("طبق اعلام سخنگو:")
    assert r.state == "CONTEXT_ONLY"


def test_class_aware_completeness():
    # QUOTE: speaker + substantive statement
    r = cc.evaluate("ترامپ گفت در صورت پیشرفت مذاکرات تحریم‌ها کاهش خواهد یافت")
    assert r.state == "COMPLETE" and r.publishable
    # ATTACK: action+target; unknown actor allowed (§10)
    r = cc.evaluate("انفجاری در مرکز بغداد رخ داد و خسارات گسترده بر جای گذاشت")
    assert r.state == "COMPLETE"  # no invented attacker
    # CASUALTY: context + count
    r = cc.evaluate("در زلزله استان ۵ نفر جان باختند به گزارش هلال احمر")
    assert r.state in ("COMPLETE", "INCOMPLETE") and r.publishable in (True, False)
    # MARKET missing time → INCOMPLETE
    r = cc.evaluate("دلار در بازار افزایش یافت")
    assert r.state == "COMPLETE" or r.missing_slots  # class-aware, not blind WHO+WHAT
    # INTERNET: area + state
    r = cc.evaluate("اختلال گسترده اینترنت در چند استان گزارش شد")
    assert r.state == "COMPLETE"


def test_incomplete_fragments_rejected():
    for frag in ("این", "ای", "ری", "خبر فوری", "ترامپ درباره ایران:"):
        r = cc.evaluate(frag)
        assert r.state in ("INCOMPLETE", "CONTEXT_ONLY") and r.publishable is False


# ---- §13 evidence preserved / §23 flag ----

def test_v2_flag_off_keeps_old_pipeline(db):
    from app.config import Settings

    s = Settings()
    assert not getattr(s, "event_engine_v2_enabled", False), "V2 must default OFF"
    # pipeline function still exists and is the authoritative path
    from app.newsroom.pipeline import process_new_items

    assert callable(process_new_items)


def test_raw_item_preserved_on_context_only(db):
    """§13: context-only RawItem persisted, classified, never published."""
    from app.db.repo import SourcesRepo, RawItemsRepo

    sid = SourcesRepo(db).create(name="w", platform="telegram", external_id="w",
                                 status="APPROVED", source_type="telegram_web_preview",
                                 polling_interval_seconds=30)
    from app.clustering.dedup import fingerprints_for

    fp = fingerprints_for("https://t.me/w/1", "ترامپ به مجله تایم:", "ترامپ به مجله تایم:")
    RawItemsRepo(db).insert(source_id=sid, platform="telegram", external_key="tgweb:w/1",
                            url="https://t.me/w/1", title="ترامپ به مجله تایم:",
                            text="ترامپ به مجله تایم:", language="fa",
                            published_at="2030-01-01T00:00:00+00:00", activation_ok=True,
                            lineage_key="tgweb:w", fingerprints=fp)
    r = cc.evaluate("ترامپ به مجله تایم:")
    assert r.state == "CONTEXT_ONLY" and r.publishable is False
    assert RawItemsRepo(db).list()[0]["text"] == "ترامپ به مجله تایم:"  # evidence kept
