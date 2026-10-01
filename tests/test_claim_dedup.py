"""P3-C — claim dedup/compare + provenance. TDD fixtures for the §4 table."""
import pytest

from app.newsroom.claim_compare import compare, resolve_or_insert_claim
from app.db.repo import SourcesRepo
from app.newsroom.claim_model import StructuredClaim, ClaimClass, extract_structured


def _claim(text, cls=ClaimClass.QUOTE, actor="ترامپ", source_item_id=1, quantity=None,
           location=None, certainty=None):
    c = extract_structured(text, source_item_id=source_item_id, speaker_hint=actor)
    c.claim_class = cls
    if quantity:
        c.quantity = quantity
    if location:
        c.location = location
    if certainty:
        c.certainty = certainty
    c.compute_fingerprint()
    return c


# ---- §4 required decisions ----

def test_exact_equivalent_same_claim():
    a = _claim("ترامپ گفت احتمال توافق با ایران وجود دارد")
    b = _claim("ترامپ گفت احتمال توافق با ایران وجود دارد")
    assert compare(a, b).decision == "SAME_CLAIM"


def test_safe_paraphrase_same_claim():
    a = _claim("ترامپ گفت احتمال توافق با ایران وجود دارد")
    b = _claim("ترامپ از امکان دستیابی به توافق با ایران سخن گفت")
    assert compare(a, b).decision == "SAME_CLAIM"


def test_actor_reversal_never_same():
    a = _claim("ایران به آمریکا حمله کرد", cls=ClaimClass.ATTACK, actor="ایران")
    b = _claim("آمریکا به ایران حمله کرد", cls=ClaimClass.ATTACK, actor="آمریکا")
    assert compare(a, b).decision in ("NEW_CLAIM", "POTENTIAL_CONTRADICTION")
    assert "ACTOR_DIFFERS" in compare(a, b).conflicts


def test_pos_vs_neg_potential_contradiction():
    a = _claim("ترامپ گفت حمله انجام خواهد شد")
    b = _claim("ترامپ گفت حمله انجام نخواهد شد")
    d = compare(a, b)
    assert d.decision == "POTENTIAL_CONTRADICTION" and "NEGATION_DIFFERS" in d.conflicts


def test_10_vs_12_casualties_potential_contradiction():
    a = _claim("۱۰ نفر کشته شدند", cls=ClaimClass.CASUALTY, quantity="10")
    b = _claim("۱۲ نفر کشته شدند", cls=ClaimClass.CASUALTY, quantity="12")
    d = compare(a, b)
    assert d.decision == "POTENTIAL_CONTRADICTION" and "NUMBERS_DIFFER" in d.conflicts


def test_later_casualty_update_new_claim():
    a = _claim("۵ نفر زخمی شدند", cls=ClaimClass.CASUALTY, quantity="5")
    b = _claim("۱۲ نفر زخمی شدند", cls=ClaimClass.CASUALTY, quantity="12")
    assert compare(a, b).decision in ("NEW_CLAIM", "POTENTIAL_CONTRADICTION")


def test_additive_location_new_claim():
    a = _claim("انفجاری در منطقه مرزی رخ داد", cls=ClaimClass.ATTACK, location="مرز شرقی")
    b = _claim("انفجاری در غرب کشور رخ داد", cls=ClaimClass.ATTACK, location="غرب کشور")
    d = compare(a, b)
    assert d.decision in ("NEW_CLAIM", "POTENTIAL_CONTRADICTION")


def test_different_target_new_claim():
    a = _claim("حمله به پایگاه نظامی در عراق انجام شد", cls=ClaimClass.ATTACK,
               location="عراق")
    b = _claim("حمله به ساختمان دولتی در تهران انجام شد", cls=ClaimClass.ATTACK,
               location="تهران")
    assert compare(a, b).decision in ("NEW_CLAIM", "POTENTIAL_CONTRADICTION")


def test_asserted_vs_may_never_same():
    a = _claim("ترامپ گفت حمله انجام خواهد شد")
    b = _claim("گفته می‌شود حمله انجام خواهد شد")
    d = compare(a, b)
    assert d.decision in ("NEW_CLAIM", "AMBIGUOUS_CLAIM", "POTENTIAL_CONTRADICTION")


def test_insufficient_structure_ambiguous():
    a = _claim("تحولات منطقه ادامه دارد")
    b = _claim("تحولات منطقه پیگیری می‌شود")
    d = compare(a, b)
    assert d.decision in ("AMBIGUOUS_CLAIM", "NEW_CLAIM")


# ---- §6 provenance / §7 resolve_or_insert ----

def _seed_event(db):
    SourcesRepo(db).create(name="s", platform="rss", url="u", status="APPROVED")
    db.execute("INSERT INTO events(title,status,first_seen_at,last_seen_at) VALUES('e','NEW','2030-01-01','2030-01-01')")
    eid = db.query_one("SELECT last_insert_rowid() i")["i"]  # capture BEFORE raw_items
    for iid in range(1, 60):
        db.execute("INSERT OR IGNORE INTO raw_items(id,source_id,platform,external_key,"
                   "fetched_at,activation_ok) VALUES(?,?,?,?,datetime('now'),1)",
                   (iid, 1, "rss", "k%d" % iid))
    return eid


def test_resolve_insert_new_claim(db):
    eid = _seed_event(db)
    c = _claim("ترامپ گفت احتمال توافق وجود دارد", source_item_id=11)
    cid, d = resolve_or_insert_claim(db, eid, c, source_item_id=11)
    assert d.decision == "NEW_CLAIM"
    prov = db.query_one("SELECT * FROM claim_source_items WHERE claim_id=?", (cid,))
    assert prov and prov["source_item_id"] == 11


def test_same_claim_two_rawitems_one_canonical_two_provenance(db):
    eid = _seed_event(db)
    c1 = _claim("ترامپ گفت احتمال توافق با ایران وجود دارد", source_item_id=21)
    cid, _ = resolve_or_insert_claim(db, eid, c1, source_item_id=21)
    c2 = _claim("ترامپ از امکان دستیابی به توافق با ایران سخن گفت", source_item_id=22)
    cid2, d2 = resolve_or_insert_claim(db, eid, c2, source_item_id=22)
    assert d2.decision == "SAME_CLAIM" and cid2 == cid  # canonical reuse
    provs = db.query("SELECT source_item_id FROM claim_source_items WHERE claim_id=?", (cid,))
    assert sorted(p["source_item_id"] for p in provs) == [21, 22]
    assert db.query_one("SELECT COUNT(*) c FROM claims WHERE event_id=?", (eid,))["c"] == 1


def test_contradiction_inserts_distinct_claim(db):
    eid = _seed_event(db)
    c1 = _claim("۱۰ نفر کشته شدند", cls=ClaimClass.CASUALTY, source_item_id=31, quantity="10")
    cid1, _ = resolve_or_insert_claim(db, eid, c1, source_item_id=31)
    c2 = _claim("۱۲ نفر کشته شدند", cls=ClaimClass.CASUALTY, source_item_id=32, quantity="12")
    cid2, d2 = resolve_or_insert_claim(db, eid, c2, source_item_id=32)
    assert d2.decision == "POTENTIAL_CONTRADICTION" and cid2 != cid1
    assert db.query_one("SELECT COUNT(*) c FROM claims WHERE event_id=?", (eid,))["c"] == 2


def test_same_rawitem_twice_idempotent(db):
    eid = _seed_event(db)
    c = _claim("ترامپ گفت احتمال توافق وجود دارد", source_item_id=41)
    cid1, d1 = resolve_or_insert_claim(db, eid, c, source_item_id=41)
    cid2, d2 = resolve_or_insert_claim(db, eid, c, source_item_id=41)
    assert cid1 == cid2 and d2.decision == "SAME_CLAIM"
    provs = db.query("SELECT source_item_id FROM claim_source_items WHERE claim_id=?", (cid1,))
    assert len(provs) == 1


def test_deterministic_repeated_compare():
    a = _claim("ترامپ گفت احتمال توافق با ایران وجود دارد")
    b = _claim("ترامپ از امکان دستیابی به توافق با ایران سخن گفت")
    results = {compare(a, b).decision for _ in range(5)}
    assert results == {"SAME_CLAIM"}
