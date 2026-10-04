"""FINAL-HARDENING regressions (§1-§8).

CI parity (registry artifact), 90% Iran target + material classifier,
crisis state-machine semantics, durable 500/60 caps with lifecycle guards,
callback permission matrix, album debounce, admin pages, Iran watchdog.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.db.repo import SettingsRepo
from app.editorial import intake as intake_mod
from app.editorial.intake import EditorialIntake
from app.newsroom.iran_policy import (
    IRAN_SHARE_TARGET, crisis_active, is_iran_related, update_crisis_mode)
from app.verification.gates import decide_claim_state

_TS = "2030-01-01T00:00:00+00:00"
_NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- §1 CI parity
def test_registry_artifact_is_committed():
    ROOT = Path(__file__).resolve().parent.parent
    f = ROOT / "data" / "source_registry_endpoints.json"
    assert f.exists(), "clean-checkout must contain the sanitized registry"
    data = json.loads(f.read_text(encoding="utf-8"))
    assert len(data) >= 100 and len({e["entity"].lower() for e in data}) == 78


# ------------------------------------------------- §2 Iran 90% + classification
def test_iran_target_is_90():
    assert IRAN_SHARE_TARGET == 0.90


def test_iran_classifier_positive_fixtures():
    positives = [
        "حمله موشکی به زیرساخت نظامی ایران",
        "تهران تحریم‌های جدید غرب را محکوم کرد",
        "IRGC commander warns of regional escalation",
        "دلار تهران مرز جدید را رد کرد",
        "قطعی اینترنت در استان خوزستان",
        "آژانس از دسترسی به سایت نطنز خبر داد",
        "ناو آمریکایی وارد خلیج فارس شد",
        "مذاکرات هسته‌ای وین ادامه یافت",
    ]
    for p in positives:
        assert is_iran_related(p), p


def test_iran_classifier_negative_fixtures():
    negatives = [
        "فوتبال: فینال جام جهانی",              # generic sport
        "فیلم جدید در-box-office هالیوود",       # entertainment
        "قیمت ططا در بازار جهانی",               # unrelated typo noise
        "استرالیا اینترنت rural را گسترش داد",    # internet ≠ Iran
        "US inflation rose 3 percent",           # world economy
    ]
    for n in negatives:
        assert not is_iran_related(n), n


# ---------------------------------------------------- §3 crisis state machine
def _seed_trigger(db, i):
    db.execute(
        "INSERT INTO events (title, status, verification, importance,"
        " velocity, first_seen_at, last_seen_at)"
        " VALUES ('حمله به ایران', 'NEW', 'UNVERIFIED', 95, 95, ?, ?)",
        (_TS, _TS))
    eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
    db.execute(
        "INSERT INTO stories (event_id, slug, headline, lead, draft_json,"
        " version, status, created_at, updated_at)"
        " VALUES (?, ?, 'حمله موشکی به ایران', 'لید', '{}', 1, 'DRAFT',"
        " ?, ?)", (eid, f"cr{i}", _NOW, _NOW))


def test_crisis_activation_persistence_extension_expiry(db):
    _seed_trigger(db, 1)
    _seed_trigger(db, 2)
    st = update_crisis_mode(db, calm_minutes=60)
    assert st["active"] is True
    assert crisis_active(db) is True

    # ACTIVE + no fresh trigger + now < until → REMAIN ACTIVE (no early exit)
    db.execute("UPDATE stories SET created_at=?",
               ((datetime.now(timezone.utc) - timedelta(hours=2))
                .isoformat(timespec="seconds"),))
    st2 = update_crisis_mode(db, calm_minutes=60)
    assert st2["active"] is True, "must not exit before until"
    assert crisis_active(db) is True

    # a fresh trigger EXTENDS the expiry
    _seed_trigger(db, 3)
    _seed_trigger(db, 4)
    st3 = update_crisis_mode(db, calm_minutes=60)
    assert st3["active"] and st3["until"] >= st2["until"]

    # expiry only after the actual calm interval
    db.execute("UPDATE settings SET value=json_set(value, '$.until',"
               " '2020-01-01T00:00:00+00:00') WHERE key='IRAN_CRISIS_MODE'")
    db.execute("UPDATE stories SET created_at='2020-01-01T00:00:00+00:00'")
    st4 = update_crisis_mode(db, calm_minutes=60)
    assert st4["active"] is False and crisis_active(db) is False

    # restart persistence: state survives a fresh read without update
    SettingsRepo(db).set("IRAN_CRISIS_MODE", json.dumps(
        {"active": True, "until": "2099-01-01T00:00:00+00:00"}))
    assert crisis_active(db) is True


def test_crisis_keeps_highrisk_single_source_blocked(db):
    _seed_trigger(db, 9)
    _seed_trigger(db, 10)
    update_crisis_mode(db, calm_minutes=60)
    assert decide_claim_state("۲۰ کشته در حمله", independent_sources=1,
                              has_contradiction=False, risk="high") \
        == "SINGLE_SOURCE"  # verification NEVER weakens in crisis


# ------------------------------------------------------ §4 durable caps 500/60
def test_config_defaults_durable():
    from app.config import Settings
    s = Settings()
    assert s.max_posts_per_day == 500
    assert s.max_posts_per_hour == 60
    # lifecycle guards must not silently cut the 60/hour global capacity
    assert s.max_provisional_posts_per_hour >= 45
    assert s.max_confirmed_posts_per_hour >= 60


def test_cap_boundary_semantics(db):
    from app.db.repo import PublicationsRepo
    pubs = PublicationsRepo(db)

    def sent(n, story, when):
        db.execute(
            "INSERT INTO events (title, status, verification, first_seen_at,"
            " last_seen_at) VALUES ('t', 'NEW', 'UNVERIFIED', ?, ?)", (_TS, _TS))
        eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
        db.execute(
            "INSERT INTO stories (event_id, slug, headline, lead, draft_json,"
            " version, status, created_at, updated_at)"
            " VALUES (?, ?, 'خبر', 'لید', '{}', 1, 'PUBLISHED', ?, ?)",
            (eid, f"s{story}", when, when))
        sid = db.query_one("SELECT MAX(id) id FROM stories")["id"]
        db.execute(
            "INSERT INTO publications (story_id, platform, payload_hash,"
            " attempt, status, created_at, updated_at)"
            " VALUES (?, 'telegram', ?, 1, 'SENT', ?, ?)",
            (sid, f"h{story}", when, when))

    now = datetime.now(timezone.utc)
    w = now.isoformat(timespec="seconds")
    # 499 prior first-sends today → the 500th is allowed
    for i in range(499):
        sent(i, f"a{i}", w)
    assert pubs.new_posts_since(now - timedelta(hours=24)) == 499
    sent(999, "the-500th", w)
    assert pubs.new_posts_since(now - timedelta(hours=24)) == 500  # boundary
    # an EDIT refreshes updated_at on an OLD row — consumes zero
    # (the original send must predate the 24h window entirely)
    old = now - timedelta(hours=30)
    sent(1000, "edited-old", old.isoformat(timespec="seconds"))
    db.execute("UPDATE publications SET updated_at=? WHERE story_id=("
               " SELECT id FROM stories WHERE slug='edited-old')", (w,))
    assert pubs.new_posts_since(now - timedelta(hours=24)) == 500


def test_throttled_never_fails_permanently():
    from app.jobs.runner import Throttled
    t = Throttled(300.0)
    assert t.retry_in_seconds == 300.0
    assert "retry" in str(t)


# ------------------------------------------- §5 callback permission matrix
class _Rec:
    def __init__(self):
        self.calls = []

    async def __call__(self, method, payload):
        self.calls.append((method, payload))
        if method == "sendMessage":
            return {"ok": True, "result": {"message_id": 77}}
        return {"ok": True}


def _seed_sub(db, uid="55001", perms=None, role="EDITOR"):
    perms = perms or {}
    db.execute(
        "INSERT OR IGNORE INTO bot_admins (telegram_user_id, display_name,"
        " role, enabled, can_submit, can_publish, can_edit, can_cancel,"
        " can_manage_admins, created_at, updated_at)"
        " VALUES (?, 'تست', ?, 1, ?, ?, ?, ?, ?, ?, ?)",
        (uid, role,
         perms.get("can_submit", 1), perms.get("can_publish", 0),
         perms.get("can_edit", 0), perms.get("can_cancel", 0),
         perms.get("can_manage_admins", 0), _TS, _TS))
    db.execute(
        "INSERT OR IGNORE INTO sources (name, platform, external_id, url,"
        " language, category, source_type, status, enabled, priority, notes,"
        " created_at, identity, verification_allowed,"
        " can_increase_independent_count)"
        " VALUES ('Manual Editorial Submission', 'telegram', 'ManualEditorial',"
        " '', 'fa', 'manual', 'direct', 'APPROVED', 1, 90, '', ?,"
        " 'ManualEditorial', 0, 0)", (_TS,))
    db.execute(
        "INSERT INTO raw_items (source_id, platform, external_key, url, title,"
        " text, language, fetched_at, activation_ok, processed_state)"
        " VALUES ((SELECT id FROM sources WHERE identity='ManualEditorial'),"
        " 'telegram', ?, '', 'خبر تستی', 'متن', 'fa', ?, 0, 'NEW')",
        (f"k{uid}", _TS,))
    rid = db.query_one("SELECT MAX(id) id FROM raw_items")["id"]
    db.execute(
        "INSERT INTO manual_submissions (submitter_admin_id, telegram_chat_id,"
        " telegram_message_id, raw_item_id, status, created_at)"
        " VALUES ((SELECT id FROM bot_admins WHERE telegram_user_id=?), '42',"
        " '7', ?, 'PREVIEW', ?)", (uid, rid, _TS))
    sid = db.query_one("SELECT MAX(id) id FROM manual_submissions")["id"]
    return sid, rid


def _cb(uid, sid, action):
    return {"callback_query": {
        "id": "q1", "from": {"id": int(uid)},
        "message": {"chat": {"id": 42}, "message_id": 5},
        "data": f"cb:{sid}:{action}"}}


@pytest.mark.asyncio
async def test_callback_permission_matrix(db, settings):
    cases = [
        # (action, perms, allowed)
        ("publish", {"can_publish": 0}, False),
        ("publish", {"can_publish": 1}, True),
        ("cancel",  {"can_cancel": 0}, False),
        ("cancel",  {"can_cancel": 1}, True),
        ("edit",    {"can_edit": 0}, False),
        ("edit",    {"can_edit": 1}, True),
    ]
    for i, (action, perms, allowed) in enumerate(cases):
        uid = f"7000{i}"
        sid, rid = _seed_sub(db, uid=uid, perms=perms)
        wk = EditorialIntake(db, settings)
        wk._api = _Rec()
        await wk._dispatch(_cb(uid, sid, action))
        row = db.query_one("SELECT activation_ok FROM raw_items WHERE id=?",
                           (rid,))
        if action in ("publish",):
            assert (row["activation_ok"] == 1) is allowed, (action, perms)
        elif action == "cancel":
            sub = db.query_one("SELECT status FROM manual_submissions"
                               " WHERE id=?", (sid,))
            assert (sub["status"] == "CANCELLED") is allowed, (action, perms)
        else:  # edit: no state mutation either way; denial message on reject
            sub = db.query_one("SELECT status FROM manual_submissions"
                               " WHERE id=?", (sid,))
            assert sub["status"] == "PREVIEW"
    # OWNER bypasses every permission gate
    sid, rid = _seed_sub(db, uid="700100", role="OWNER")
    wk = EditorialIntake(db, settings)
    wk._api = _Rec()
    await wk._dispatch(_cb("700100", sid, "publish"))
    assert db.query_one("SELECT activation_ok FROM raw_items WHERE id=?",
                        (rid,))["activation_ok"] == 1


@pytest.mark.asyncio
async def test_disabled_admin_callback_no_mutation(db, settings):
    sid, rid = _seed_sub(db, uid="70100", perms={"can_publish": 1})
    db.execute("UPDATE bot_admins SET enabled=0 WHERE telegram_user_id='70100'")
    wk = EditorialIntake(db, settings)
    wk._api = _Rec()
    await wk._dispatch(_cb("70100", sid, "publish"))
    assert db.query_one("SELECT activation_ok FROM raw_items WHERE id=?",
                        (rid,))["activation_ok"] == 0  # untouched


# ------------------------------------------------------- §6 album debounce
@pytest.mark.asyncio
async def test_album_debounce_single_preview(db, settings):
    db.execute(
        "INSERT INTO bot_admins (telegram_user_id, display_name, role, enabled,"
        " created_at, updated_at) VALUES ('71000', 'تست', 'EDITOR', 1, ?, ?)",
        (_TS, _TS))
    wk = EditorialIntake(db, settings)
    rec = _Rec()
    wk._api = rec
    for i in range(3):  # three album fragments in quick succession
        await wk._dispatch({"message": {
            "message_id": i + 1, "chat": {"id": 42},
            "from": {"id": 71000}, "media_group_id": "album9",
            "caption": "آلبوم تستی" if i == 0 else "",
            "photo": [{"file_id": f"af{i}", "width": 1}], "date": 1}})
    # debounce still pending → no preview yet, one raw item, order kept
    items = db.query("SELECT * FROM raw_items")
    assert len(items) == 1
    assert json.loads(items[0]["media_json"]) == [
        {"type": "photo", "file_id": "af0"},
        {"type": "photo", "file_id": "af1"},
        {"type": "photo", "file_id": "af2"}]
    subs = db.query("SELECT * FROM manual_submissions")
    assert len(subs) == 1 and subs[0]["status"] == "RECEIVED"
    assert not [c for m, c in rec.calls if m == "sendMessage"]
    # quiet period elapses → exactly ONE preview arrives
    await asyncio.sleep(intake_mod._ALBUM_DEBOUNCE_S + 0.6)
    previews = [c for m, c in rec.calls if m == "sendMessage"]
    assert len(previews) == 1
    assert db.query_one("SELECT status FROM manual_submissions")["status"] \
        == "PREVIEW"


# -------------------------------------------------- §7 admin UI pages
def test_bot_admins_page_and_permissions(admin_client):
    html = admin_client.get("/admin/bot-admins").text
    assert "مدیران ربات" in html and "شناسه عددی" in html
    csrf = admin_client.cookies.get("akh_csrf")
    r = admin_client.post("/admin/bot-admins/add", data={
        "telegram_user_id": "72222", "display_name": "ویراستار",
        "role": "EDITOR", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303
    assert "72222" in admin_client.get("/admin/bot-admins").text
    # CSRF enforced
    r2 = admin_client.post("/admin/bot-admins/add", data={
        "telegram_user_id": "73333", "role": "EDITOR"}, follow_redirects=False)
    assert r2.status_code != 303


def test_editorial_inbox_page(admin_client):
    html = admin_client.get("/admin/editorial-inbox").text
    assert "صندوق تحریریه" in html
    csrf = admin_client.cookies.get("akh_csrf")
    r = admin_client.post("/admin/editorial-inbox/999/action", data={
        "action": "approve", "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303  # unknown id → safe no-op redirect


# ------------------------------------------------- §8 Iran stall watchdog
def test_iran_stall_watchdog(db, settings):
    from app.ingestion.scheduler import _iran_stall_check
    # no SEND for >10m + an Iran-ready story → marker set, jobs nudged
    old = (datetime.now(timezone.utc) - timedelta(minutes=30)) \
        .isoformat(timespec="seconds")
    # an OLD published story provides the stale last-SEND timestamp
    db.execute(
        "INSERT INTO events (title, status, verification, first_seen_at,"
        " last_seen_at) VALUES ('قدیمی', 'NEW', 'UNVERIFIED', ?, ?)", (_TS, _TS))
    old_eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
    db.execute(
        "INSERT INTO stories (event_id, slug, headline, lead, draft_json,"
        " version, status, created_at, updated_at)"
        " VALUES (?, 'w0', 'خبر قدیمی', 'لید', '{}', 1, 'PUBLISHED', ?, ?)",
        (old_eid, old, old))
    old_sid = db.query_one("SELECT MAX(id) id FROM stories")["id"]
    db.execute(
        "INSERT INTO publications (story_id, platform, payload_hash, attempt,"
        " status, created_at, updated_at) VALUES (?, 'telegram', 'h8', 1,"
        " 'SENT', ?, ?)", (old_sid, old, old))
    # the Iran-ready story has NO publication (waiting to go out)
    db.execute(
        "INSERT INTO events (title, status, verification, first_seen_at,"
        " last_seen_at) VALUES ('تحریم ایران', 'NEW', 'UNVERIFIED', ?, ?)",
        (_TS, _TS))
    eid = db.query_one("SELECT MAX(id) id FROM events")["id"]
    db.execute(
        "INSERT INTO stories (event_id, slug, headline, lead, draft_json,"
        " version, status, created_at, updated_at)"
        " VALUES (?, 'w1', 'تحریم جدید علیه ایران', 'لید', '{}', 1, 'DRAFT',"
        " ?, ?)", (eid, _NOW, _NOW))
    sid = db.query_one(
        "SELECT id FROM stories WHERE slug='w1'")["id"]
    db.execute(
        "INSERT INTO jobs (job_type, status, payload_json, dedupe_key,"
        " priority, run_after, created_at, updated_at)"
        " VALUES ('publish_send', 'pending', '{}', 'j1', 100, '2099-01-01',"
        " ?, ?)", (_NOW, _NOW))
    _iran_stall_check(db, settings)
    marker = SettingsRepo(db).get("IRAN_PUBLICATION_PIPELINE_STALLED")
    assert marker and "iran_stories_ready" in marker
    nudged = db.query_one("SELECT run_after FROM jobs WHERE dedupe_key='j1'")
    fresh_now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    assert nudged["run_after"] <= fresh_now  # bounded safe recovery
    # a fresh SEND clears the marker
    db.execute("UPDATE publications SET created_at=? WHERE story_id=?",
               (_NOW, old_sid))
    _iran_stall_check(db, settings)
    assert SettingsRepo(db).get("IRAN_PUBLICATION_PIPELINE_STALLED") == ""
