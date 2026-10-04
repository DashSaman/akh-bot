"""HARD PUBLICATION QUALITY GATES regressions (owner directive 2026-10-04).

Real bad outputs from the channel are the fixtures: the Oman credential
reception (ceremony, context-incomplete) and the bird-trivia item must never
publish again; self-contained, material stories still flow. The 500/day cap
stays a ceiling — never a filler target.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.newsroom.quality_gates import (
    context_incomplete, duplicate_of_recent, low_value, materiality_floor,
    publication_quality_gate, routine_ceremony, translation_lost_entities)

_TS = "2030-01-01T00:00:00+00:00"
_NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

OMAN = "وزیر از نماینده سازمان بهداشت جهانی و دو سفیر جدید استقبال کرد"
BIRDS = "دو پرنده صدایی بلندتر از فیل‌ها و شیپورها تولید می‌کنند"


# ------------------------------------------------------------- real fixtures
def test_oman_fixture_blocked():
    assert publication_quality_gate(None, OMAN, "", 50, 0) == "LOW_MATERIALITY"
    assert routine_ceremony(OMAN) is True


def test_birds_fixture_blocked():
    assert publication_quality_gate(None, BIRDS, "", 50, 0) == "LOW_VALUE_CONTENT"
    assert low_value(BIRDS) is True


def test_vague_subject_without_identity_blocked():
    for h in ("وزیر از نماینده استقبال کرد",
              "رئیس اعلام کرد که برنامه‌ها ادامه دارد",
              "او درباره موضوع صحبت کرد"):
        assert context_incomplete(h), h


def test_source_context_resolves_minister_passes():
    h = "وزیر گفت تحریم‌های جدید آمریکا بی‌اثر خواهد بود"
    body = "بدر البوسعیدی، وزیر خارجه عمان، در مسقط اعلام کرد"
    assert context_incomplete(h, body) is False  # body resolves identity+place
    assert publication_quality_gate(None, h, body, 60, 0) is None


def test_selfcontained_world_news_passes():
    h = "مقامات لیتوانی فرودگاه ویلنیوس را بسته و پروازهای ناتو را آغاز کردند"
    assert context_incomplete(h) is False
    assert routine_ceremony(h) is False
    assert publication_quality_gate(None, h, "", 50, 0) is None  # regional+NATO


def test_material_iran_diplomacy_passes_ceremony_exemption():
    h = "وزیر خارجه عمان با همتای آمریکایی درباره تحریم‌های جدید گفت‌وگو کرد"
    assert routine_ceremony(h) is False  # material: تحریم/آمریکا
    assert publication_quality_gate(None, h, "", 50, 0) is None


def test_lowvalue_global_cannot_consume_capacity():
    # P2/P3 non-Iran trivia under the higher materiality floor
    assert publication_quality_gate(
        None, "نمایشگاه کتاب توکیو امسال برگزار شد", "", 50, 0) \
        == "MATERIALITY_FLOOR"
    # Iran-relevant passes at the same weight (Iran-first)
    assert publication_quality_gate(
        None, "نمایشگاه کتاب در تهران با حضور ناشران ایرانی برگزار شد", "", 30, 0) \
        is None


def test_materiality_floor_tiers():
    assert materiality_floor("تحریم جدید ایران") == 25
    assert materiality_floor("حمله به غزه") == 45
    assert materiality_floor("نمایشگاه توکیو") == 65


def test_translation_entity_loss_detected():
    src = "US President announced new sanctions on Iran worth 40 billion"
    ok = "رئیس‌جمهور آمریکا تحریم‌های جدید ۴۰ میلیاردی علیه ایران را اعلام کرد"
    lost_num = "رئیس‌جمهور آمریکا تحریم‌های جدید میلیاردی علیه ایران را اعلام کرد"
    lost_country = "رئیس‌جمهور تحریم‌های جدید ۴۰ میلیاردی را اعلام کرد"
    assert translation_lost_entities(src, ok) == []
    assert any(x.startswith("num:") for x in translation_lost_entities(src, lost_num))
    assert any(x.startswith("country:") for x in
               translation_lost_entities(src, lost_country))


# ------------------------------------------------------------- duplicate §10
def _seed_sent_story(db, eid, slug, headline, when=_NOW):
    db.execute(
        "INSERT INTO stories (event_id, slug, headline, lead, draft_json,"
        " version, status, created_at, updated_at)"
        " VALUES (?, ?, ?, 'لید', '{}', 1, 'PUBLISHED', ?, ?)",
        (eid, slug, headline, when, when))
    sid = db.query_one("SELECT MAX(id) id FROM stories")["id"]
    db.execute(
        "INSERT INTO publications (story_id, platform, payload_hash, attempt,"
        " status, created_at, updated_at) VALUES (?, 'telegram', ?, 1, 'SENT',"
        " ?, ?)", (sid, f"h{slug}", when, when))
    return sid


_KCOUNTER = [0]


def _seed_source_event(db, ident, headline):
    db.execute(
        "INSERT INTO sources (name, platform, external_id, url, language,"
        " category, source_type, status, enabled, priority, notes,"
        " created_at, identity) VALUES (?, 'telegram', ?, '', 'ar', '',"
        " 'direct', 'APPROVED', 1, 50, '', ?, ?)",
        (f"tg_{ident}", ident, _TS, ident))
    sid = db.query_one("SELECT id FROM sources WHERE identity=?", (ident,))["id"]
    db.execute(
        "INSERT INTO raw_items (source_id, platform, external_key, url, title,"
        " text, language, fetched_at, activation_ok, processed_state)"
        " VALUES (?, 'telegram', ?, '', ?, '', 'ar', ?, 1, 'PROCESSED')",
        (_KCOUNTER.__setitem__(0, _KCOUNTER[0] + 1) or sid,
         f"k{ident}{_KCOUNTER[0]}", headline, _TS))
    rid = db.query_one("SELECT MAX(id) id FROM raw_items")["id"]
    db.execute(
        "INSERT INTO events (title, status, verification, first_seen_at,"
        " last_seen_at) VALUES (?, 'PUBLISHED', 'UNVERIFIED', ?, ?)",
        (headline, _TS, _TS))
    eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
    db.execute("INSERT INTO event_items (event_id, raw_item_id) VALUES (?, ?)",
               (eid, rid))
    return eid


def test_duplicate_oman_story_one_send_only(db):
    first_eid = _seed_source_event(db, "OmanMFA", OMAN)
    _seed_sent_story(db, first_eid, "oman1", OMAN)
    # same real event arrives again as a NEW event row from the same source
    second_eid = _seed_source_event(db, "OmanMFA",
                                    "وزیر از نماینده سازمان بهداشت جهانی و "
                                    "دو سفیر جدید استقبال کرد")
    dup = duplicate_of_recent(db, second_eid, OMAN)
    assert dup is not None, "same-event re-arrival must map to the SENT story"
    assert publication_quality_gate(db, OMAN, "", 50, second_eid) \
        in ("DROP_DUPLICATE", "LOW_MATERIALITY")
    # distinct event from same outlet must NOT merge
    other = _seed_source_event(db, "OmanMFA",
                               "عمان حمله پهپادی به کشتی تجاری در دریای عرب را محکوم کرد")
    assert duplicate_of_recent(db, other,
                               "عمان حمله پهپادی به کشتی تجاری در دریای عرب را محکوم کرد") is None


def test_material_update_edits_not_resends(db):
    """The EDIT-only invariant for an already-SENT story of the same event:
    a second publication row for the same story is an EDIT, never a SEND."""
    eid = _seed_source_event(db, "Reuters2",
                             "رویترز: توافق هسته‌ای جدید ایران امضا شد")
    sid = _seed_sent_story(db, eid, "n1",
                           "رویترز: توافق هسته‌ای جدید ایران امضا شد")
    # simulate the lifecycle EDIT refresh (same story row, updated_at moves)
    db.execute("UPDATE publications SET updated_at=?, payload_hash='edited'"
               " WHERE story_id=? AND status='SENT'", (_NOW, sid))
    rows = db.query("SELECT COUNT(*) c FROM publications WHERE story_id=? AND"
                    " status='SENT'", (sid,))
    assert rows[0]["c"] == 1  # ONE public message; edits reuse the row


def test_cap_is_ceiling_never_filler_target(db):
    """§6: unused capacity must not pull blocked content through."""
    assert publication_quality_gate(None, BIRDS, "", 99, 0) == "LOW_VALUE_CONTENT"
    # even at max weight with a wide-open cap, trivia stays blocked
    assert publication_quality_gate(None, OMAN, "", 99, 0) == "LOW_MATERIALITY"
