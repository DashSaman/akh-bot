"""P3-E — story evolution + SEND/EDIT invariant, live through the V2 pipeline.

Required fixtures (Part-3 finish spec §2/§4/§11):
- 6-fragment interview → 1 Event → 1 Story → 1 SEND
- already-published event + new material claim → StoryVersion++ → EDIT same message
- existing SENT publication ⇒ publish_send forbidden (runner-side hard guard)
- non-material claim → evidence stored, message untouched
- debounce: 5 rapid updates → ONE consolidated EDIT; critical bypasses
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.db.repo import PublicationsRepo, RawItemsRepo, SourcesRepo, utcnow
from app.jobs.runner import make_edit_handler, make_send_handler
from app.newsroom.v2_pipeline import process_new_items_v2

T0 = "2026-10-03T10:00:00+00:00"


class Brand:
    short_name = "راسته"
    name_fa = "راسته"
    tagline_fa = "خبر و راستی‌آزمایی"
    telegram_handle = "RastehNews"


class FakePublisher:
    platform = "telegram"

    def __init__(self):
        self.calls = []
        self.chat_id = "@testchannel"

    async def send_message(self, text):
        self.calls.append(("send", text))
        return {"ok": True, "message_id": str(100 + len(self.calls))}

    async def edit_message(self, mid, text):
        self.calls.append(("edit", mid, text))
        return {"ok": True}


def _settings(settings):
    return settings.model_copy(update={
        "event_engine_v2_enabled": True,
        "edit_debounce_seconds": 120,
        "max_public_story_details": 5,
    })


def _ts(minutes: int) -> str:
    return (datetime.fromisoformat(T0) + timedelta(minutes=minutes)).isoformat()


def _source(db, name="src_a"):
    sid = SourcesRepo(db).create(name=name, platform="telegram", url=f"t.me/{name}",
                                 status="APPROVED", verification_allowed=False,
                                 publication_policy="AUTO")
    SourcesRepo(db).update(sid, source_control_state="OWNER_ENABLED")
    return sid


def _item(db, source_id, key, text, minutes=0):
    return RawItemsRepo(db).insert(
        source_id=source_id, platform="telegram", external_key=key, title="", text=text,
        published_at=_ts(minutes), activation_ok=True)


PREFIX = "ترامپ به مجله تایم:"


def _interview_items(db, sid, n=5):
    _item(db, sid, "f0", PREFIX, 0)
    frags = [
        "هیچ توافقی حاصل نشده است و مذاکرات به شکل جدی ادامه دارد",
        "او گفت مذاکرات در حال حاضر ادامه دارد و متوقف نشده است",
        "در ادامه افزود: مذاکرات درباره پرونده هسته‌ای با تمرکز ادامه دارد",
        "همچنین گفت: هیچ توافقی حاصل نشده و راه ادامه دارد",
        "تأکید کرد که توافق نهایی به شرایط وابسته است و هنوز قطعی نیست",
    ]
    for i, t in enumerate(frags[:n]):
        _item(db, sid, f"f{i + 1}", t, (i + 1) * 2)
    return frags


# ---- §4 required fixture: 6 fragments → 1 Event → 1 Story → 1 SEND ----

def test_six_fragment_interview_single_event_story_send(db, settings):
    s = _settings(settings)
    sid = _source(db)
    _interview_items(db, sid)
    summary = process_new_items_v2(db, Brand(), s)

    events = db.query("SELECT * FROM events")
    stories = db.query("SELECT * FROM stories")
    sends = db.query("SELECT * FROM jobs WHERE job_type='publish_send'")
    assert len(events) == 1, f"interview fragments must share ONE event, got {len(events)}"
    assert len(stories) == 1, f"ONE story per event, got {len(stories)}"
    assert len(sends) == 1, f"exactly one SEND intent, got {len(sends)}"
    assert summary["sends"] == 1
    # meaningful standalone Persian headline — never a raw fragment
    payload = json.loads(sends[0]["payload_json"])
    from app.publishing.telegram_bot import is_persian_public_text
    from app.verification.gates import is_valid_headline
    assert stories[0]["headline"] and is_valid_headline(stories[0]["headline"])
    assert is_persian_public_text(payload["text"])
    assert "فوری" not in payload["text"].split("\n")[0]
    # replay-safe: further passes enqueue nothing new
    process_new_items_v2(db, Brand(), s)
    process_new_items_v2(db, Brand(), s)
    assert db.query_one("SELECT COUNT(*) AS n FROM jobs WHERE job_type='publish_send'")["n"] == 1


# ---- hard invariant: existing SENT ⇒ SEND forbidden, updates EDIT ----

def _mark_sent(db, story_id, remote_id="555"):
    pub = db.query_one(
        "SELECT * FROM publications WHERE story_id=? ORDER BY id DESC LIMIT 1", (story_id,))
    PublicationsRepo(db).mark(pub["id"], "SENT", remote_id=remote_id)
    db.execute("UPDATE publications SET chat_id=? WHERE id=?", ("@testchannel", pub["id"]))
    return pub["id"]


def test_new_material_claim_edits_same_message_never_new_send(db, settings):
    s = _settings(settings)
    sid = _source(db)
    _interview_items(db, sid)
    process_new_items_v2(db, Brand(), s)
    story = db.query_one("SELECT * FROM stories")
    _mark_sent(db, story["id"], remote_id="555")
    version_before = story["version"]

    # later material claim on the same event, same speaker (interview continues),
    # a fresh figure — NEW_NUMBERS is material; normal risk so gates allow the EDIT
    _item(db, sid, "late1",
          "هیچ‌یک از طرفین فهرست اختلافات را ارائه نکرده است و شمار جلسات به ۴۰ رسید", 20)
    summary = process_new_items_v2(db, Brand(), s)

    sends = db.query("SELECT * FROM jobs WHERE job_type='publish_send'")
    edits = db.query("SELECT * FROM jobs WHERE job_type='publish_edit'")
    assert len(sends) == 1, "no second SEND intent may appear"
    assert len(edits) == 1 and summary["edits"] == 1
    payload = json.loads(edits[0]["payload_json"])
    story_after = db.query_one("SELECT * FROM stories WHERE id=?", (story["id"],))
    assert story_after["version"] == version_before + 1, "StoryVersion must increment"
    # EDIT must target the SAME remote message via the runner
    pub = FakePublisher()
    handler = make_edit_handler(db, s, lambda: pub)
    import asyncio
    ok = asyncio.run(handler(json.loads(edits[0]["payload_json"])))
    assert ok
    assert pub.calls and pub.calls[0][0] == "edit" and pub.calls[0][1] == "555"


def test_publish_send_forbidden_when_sent_exists(db, settings):
    s = _settings(settings)
    sid = _source(db)
    _interview_items(db, sid)
    process_new_items_v2(db, Brand(), s)
    story = db.query_one("SELECT * FROM stories")
    _mark_sent(db, story["id"], remote_id="555")
    # a stale/duplicate publish_send job must be refused at execution time
    db.execute(
        "INSERT INTO jobs(job_type,payload_json,status,attempts,max_attempts,run_after,"
        "created_at,updated_at,priority) VALUES('publish_send',?,'pending',0,5,?,?,?,90)",
        (json.dumps({"story_id": story["id"], "platform": "telegram",
                     "payload_hash": "x" * 64, "text": "duplicate", "publication_id": 0}),
         utcnow(), utcnow(), utcnow()))
    pub = FakePublisher()
    handler = make_send_handler(db, s, lambda: pub)
    import asyncio
    ok = asyncio.run(handler(json.loads(db.query_one(
        "SELECT payload_json FROM jobs WHERE job_type='publish_send' AND status='pending'"
        " ORDER BY id DESC LIMIT 1")["payload_json"])))
    assert ok is True  # cancelled, not retried
    assert pub.calls == [], "send must NEVER execute when a SENT publication exists"
    row = db.query_one(
        "SELECT error FROM publications WHERE error='SEND_FORBIDDEN_EDIT_ONLY'"
        " ORDER BY id DESC LIMIT 1")
    assert row and row["error"] == "SEND_FORBIDDEN_EDIT_ONLY"


def test_non_material_claim_stores_evidence_without_edit(db, settings):
    s = _settings(settings)
    sid = _source(db)
    _interview_items(db, sid)
    process_new_items_v2(db, Brand(), s)
    story = db.query_one("SELECT * FROM stories")
    _mark_sent(db, story["id"], remote_id="555")
    db.execute("UPDATE claims SET material=0 WHERE event_id=?", (story["event_id"],))

    _item(db, sid, "rest1", "هیچ توافقی حاصل نشده است و مذاکرات با فاصله همچنان ادامه دارد", 40)
    summary = process_new_items_v2(db, Brand(), s)
    edits = db.query("SELECT * FROM jobs WHERE job_type='publish_edit'")
    assert edits == [], "restatement must not edit the public message"
    assert summary["sends"] == 0, "restatement must never create any SEND"
    events = db.query_one("SELECT COUNT(*) AS n FROM events")["n"]
    assert events == 1, "paraphrase restatement must join the existing event (REG-038)"
    claims = db.query_one("SELECT COUNT(*) AS n FROM claims")["n"]
    assert claims >= 1, "evidence is still stored"


def test_debounce_consolidates_five_rapid_updates(db, settings):
    s = _settings(settings)
    sid = _source(db)
    _interview_items(db, sid)
    process_new_items_v2(db, Brand(), s)
    story = db.query_one("SELECT * FROM stories")
    _mark_sent(db, story["id"], remote_id="555")
    db.execute("UPDATE claims SET material=0 WHERE event_id=?", (story["event_id"],))

    # five rapid material STATUS updates from the same interview voice
    updates = [
        "او افزود رایزنی‌های امروز متوقف شد",
        "رایزنی‌ها فردا از سر گرفته خواهد شد",
        "پرونده انرژی با توافق موقت همراه شد و ممنوعیت‌ها لغو شد",
        "آتش‌بس موقت برقرار شد و دیدگاه‌ها نزدیک شد",
        "حکم اولیه لغو شد و پرونده بازنگری شد",
    ]
    for i, txt in enumerate(updates):
        _item(db, sid, f"b{i}", txt, 12 + i)
        process_new_items_v2(db, Brand(), s)
    pending = db.query(
        "SELECT * FROM jobs WHERE job_type='publish_edit' AND status='pending'")
    assert len(pending) == 1, "5 rapid updates must consolidate into ONE debounced EDIT"
    payload = json.loads(pending[0]["payload_json"])
    assert "پرونده بازنگری" in payload["text"], "consolidated EDIT must carry the LATEST content"
    superseded = db.query_one(
        "SELECT COUNT(*) AS n FROM publications WHERE error='SUPERSEDED_BY_DEBOUNCE'")["n"]
    assert superseded >= 1


def test_critical_correction_bypasses_debounce(db, settings):
    s = _settings(settings)
    sid = _source(db)
    _interview_items(db, sid)
    process_new_items_v2(db, Brand(), s)
    story = db.query_one("SELECT * FROM stories")
    _mark_sent(db, story["id"], remote_id="555")
    db.execute("UPDATE claims SET material=0 WHERE event_id=?", (story["event_id"],))

    _item(db, sid, "crit1",
          "وی گفت اشتباه کردیم و تصحیح می‌کنیم: دو جلسه دیگر رایزنی خواهد شد", 14)
    process_new_items_v2(db, Brand(), s)
    job = db.query_one(
        "SELECT * FROM jobs WHERE job_type='publish_edit' ORDER BY id DESC LIMIT 1")
    assert job is not None
    run_after = datetime.fromisoformat(job["run_after"])
    now = datetime.now(timezone.utc)
    assert (run_after - now).total_seconds() < 30, "critical correction must bypass debounce"


# ---- NAYA behavior: foreign content never publishes without a translator ----

def test_arabic_content_held_needs_language_processing(db, settings):
    s = _settings(settings)
    sid = _source(db, "naya_like")
    _item(db, sid, "ar1",
          "مقتل جنود في هجوم صاروخي على قاعدة عسكرية في العراق اليوم صباحا",
          5)
    process_new_items_v2(db, Brand(), s)
    sends = db.query("SELECT * FROM jobs WHERE job_type='publish_send'")
    assert sends == [], "raw Arabic must never publish (no translation provider)"
    ev = db.query_one("SELECT status FROM events")
    assert ev and ev["status"] == "HELD"


# ---- importance floor: low-value topics stored, never published ----

def test_low_value_sport_topic_held(db, settings):
    s = _settings(settings)
    sid = _source(db, "sport_src")
    _item(db, sid, "sp1",
          "در مسابقه لیگ فوتبال، تیم باشگاه فوتبال برابر تیم فوتبال دیگر به پیروزی رسید و بازیکن گل زد",
          5)
    process_new_items_v2(db, Brand(), s)
    sends = db.query("SELECT * FROM jobs WHERE job_type='publish_send'")
    assert sends == [], "low-value sport must not crowd the public channel"
    ev = db.query_one("SELECT status FROM events")
    assert ev and ev["status"] == "HELD"
