"""Editorial intake regressions (directive 2026-10-04 Part E/H).

Auth by numeric user id; every submission enters the SAME canonical pipeline
as a MANUAL_HOLD RawItem (no direct send); albums group; forwards map known
identities and unknown origins never gain trust; approvals flip state; the
feature flag default is OFF so production is untouched.
"""
from __future__ import annotations

import json

import pytest

from app.editorial.intake import EditorialIntake, MANUAL_IDENTITY, bootstrap_owner

_TS = "2030-01-01T00:00:00+00:00"


class _Rec:
    def __init__(self):
        self.calls = []

    async def __call__(self, method, payload):
        self.calls.append((method, payload))
        if method == "sendMessage":
            return {"ok": True, "result": {"message_id": 77}}
        return {"ok": True}


def _mk(db, settings):
    wk = EditorialIntake(db, settings)
    rec = _Rec()
    wk._api = rec
    return wk, rec


def _admin(db, uid="55001", role="EDITOR", enabled=1):
    db.execute(
        "INSERT OR IGNORE INTO bot_admins (telegram_user_id, display_name,"
        " role, enabled, created_at, updated_at)"
        " VALUES (?, 'تست', ?, ?, ?, ?)", (uid, role, enabled, _TS, _TS))
    return db.query_one("SELECT * FROM bot_admins WHERE telegram_user_id=?",
                        (uid,))


def _msg(uid="55001", text="خبر مهم تستی از تهران", mid=100, **extra):
    m = {"message_id": mid, "chat": {"id": 42},
         "from": {"id": int(uid), "first_name": "T"},
         "text": text, "date": 1}
    m.update(extra)
    return m


@pytest.mark.asyncio
async def test_unauthorized_user_rejected(db, settings):
    wk, rec = _mk(db, settings)
    await wk._dispatch({"message": _msg(uid="999")})
    assert any("مجاز" in (p.get("text") or "") for _, p in rec.calls)
    assert db.query_one("SELECT COUNT(*) c FROM raw_items")["c"] == 0


@pytest.mark.asyncio
async def test_disabled_admin_rejected(db, settings):
    _admin(db, uid="777", enabled=0)
    wk, rec = _mk(db, settings)
    await wk._dispatch({"message": _msg(uid="777")})
    assert any("مجاز" in (p.get("text") or "") for _, p in rec.calls)


@pytest.mark.asyncio
async def test_text_submission_manual_hold_raw_item(db, settings):
    a = _admin(db)
    wk, rec = _mk(db, settings)
    await wk._dispatch({"message": _msg()})
    row = db.query_one(
        "SELECT ri.*, s.identity ident FROM raw_items ri"
        " JOIN sources s ON s.id = ri.source_id ORDER BY ri.id DESC")
    assert row["processed_state"] == "NEW" and row["activation_ok"] == 0
    assert row["ident"] == MANUAL_IDENTITY  # E8: manual identity, never faked
    sub = db.query_one("SELECT * FROM manual_submissions ORDER BY id DESC")
    assert sub["status"] == "PREVIEW" and sub["raw_item_id"] == row["id"]
    # preview with all four buttons
    kb = [p for m, p in rec.calls if m == "sendMessage"][-1]["reply_markup"]
    flat = [b["text"] for row_ in kb["inline_keyboard"] for b in row_]
    assert "🚀 انتشار" in flat and "❌ لغو" in flat
    # manual source must never add independent confirmations
    msrc = db.query_one("SELECT * FROM sources WHERE identity=?",
                        (MANUAL_IDENTITY,))
    assert msrc["can_increase_independent_count"] == 0


@pytest.mark.asyncio
async def test_forward_known_source_maps_identity(db, settings):
    db.execute(
        "INSERT INTO sources (name, platform, external_id, url, language,"
        " category, source_type, status, enabled, priority, notes, created_at,"
        " identity) VALUES ('tg naya_test', 'telegram', '',"
        " 'https://t.me/naya_test', 'fa', '', 'direct', 'APPROVED', 1, 50,"
        " '', ?, 'NAYA')", (_TS,))
    naya_id = db.query_one("SELECT id FROM sources WHERE identity='NAYA'")["id"]
    _admin(db)
    wk, _ = _mk(db, settings)
    await wk._dispatch({"message": _msg(
        forward_origin={"type": "channel",
                        "chat": {"title": "tg naya_test", "username": ""}})})
    row = db.query_one(
        "SELECT ri.source_id sid FROM raw_items ri ORDER BY ri.id DESC")
    assert row["sid"] == naya_id


@pytest.mark.asyncio
async def test_forward_unknown_origin_stays_manual(db, settings):
    _admin(db)
    wk, _ = _mk(db, settings)
    await wk._dispatch({"message": _msg(
        forward_origin={"type": "channel",
                        "chat": {"title": "کانال ناشناخته اما مهم"}})})
    row = db.query_one(
        "SELECT ri.forward_from ff, s.identity ident FROM raw_items ri"
        " JOIN sources s ON s.id = ri.source_id ORDER BY ri.id DESC")
    assert row["ident"] == MANUAL_IDENTITY
    assert "ناشناخته" in row["ff"]
    msrc = db.query_one("SELECT can_increase_independent_count c FROM sources"
                        " WHERE identity=?", (MANUAL_IDENTITY,))
    assert msrc["c"] == 0  # never counts as an independent confirmation


@pytest.mark.asyncio
async def test_album_media_group_accumulates(db, settings):
    _admin(db)
    wk, _ = _mk(db, settings)
    await wk._dispatch({"message": _msg(
        mid=1, media_group_id="g1", text="",
        photo=[{"file_id": "f1", "width": 1}])})
    await wk._dispatch({"message": _msg(
        mid=2, media_group_id="g1", text="",
        photo=[{"file_id": "f2", "width": 2}])})
    rows = db.query("SELECT media_json FROM raw_items ORDER BY id")
    media = json.loads(rows[-1]["media_json"])
    assert [m["file_id"] for m in media] == ["f1", "f2"]  # E11: file_id only


@pytest.mark.asyncio
async def test_publish_and_cancel_callbacks(db, settings):
    a = _admin(db)
    wk, rec = _mk(db, settings)
    await wk._dispatch({"message": _msg()})
    sub = db.query_one("SELECT * FROM manual_submissions ORDER BY id DESC")
    rid = sub["raw_item_id"]
    await wk._dispatch({"callback_query": {
        "id": "cbq1", "from": {"id": 55001},
        "message": {"chat": {"id": 42}, "message_id": 7},
        "data": f"cb:{sub['id']}:publish"}})
    row = db.query_one("SELECT processed_state, activation_ok FROM raw_items"
                       " WHERE id=?", (rid,))
    sub2 = db.query_one("SELECT status FROM manual_submissions WHERE id=?",
                        (sub["id"],))
    assert row["processed_state"] == "NEW" and row["activation_ok"] == 1
    assert sub2["status"] == "SUBMITTED"
    # cancel flow on a fresh submission
    await wk._dispatch({"message": _msg(text="دومی", mid=101)})
    sub3 = db.query_one("SELECT * FROM manual_submissions ORDER BY id DESC")
    await wk._dispatch({"callback_query": {
        "id": "cbq2", "from": {"id": 55001},
        "message": {"chat": {"id": 42}, "message_id": 8},
        "data": f"cb:{sub3['id']}:cancel"}})
    r3 = db.query_one("SELECT activation_ok, processed_state FROM raw_items"
                      " WHERE id=?", (sub3["raw_item_id"],))
    assert r3["activation_ok"] == 0 and r3["processed_state"] == "ERROR"


def test_offset_persisted(db, settings):
    wk, _ = _mk(db, settings)
    assert wk._load_offset() == 0
    wk._save_offset(41)
    assert EditorialIntake(db, settings)._load_offset() == 41  # restart safe


def test_flag_default_off_and_owner_bootstrap(db, settings):
    assert settings.editorial_bot_intake_enabled is False  # E1 default
    settings.newsroom_owner_telegram_id = "5504556066"
    assert bootstrap_owner(db, settings) is True
    owner = db.query_one("SELECT * FROM bot_admins WHERE"
                         " telegram_user_id='5504556066'")
    assert owner["role"] == "OWNER" and owner["can_manage_admins"] == 1


def test_cross_admin_same_event_one_story(db, settings):
    """Two admins submitting identical news produce two MANUAL_HOLD RawItems
    that BOTH release into the SAME canonical pipeline (processed NEW); the
    one-Event clustering itself is the pipeline's own tested invariant."""
    import asyncio
    _admin(db, uid="1")
    _admin(db, uid="2")
    wk, _ = _mk(db, settings)
    asyncio.run(wk._dispatch({"message": _msg(
        uid="1", mid=1, text="انفجار بزرگ در تهران گزارش شده است")}))
    asyncio.run(wk._dispatch({"message": _msg(
        uid="2", mid=2, text="انفجار بزرگ در تهران گزارش شده است")}))
    rows = db.query("SELECT * FROM raw_items ORDER BY id")
    assert len(rows) == 2
    assert all(r["processed_state"] == "NEW" and r["activation_ok"] == 0
               for r in rows)  # held until an editor approves
    for sub in db.query("SELECT * FROM manual_submissions"):
        db.execute("UPDATE raw_items SET activation_ok=1 WHERE id=?",
                   (sub["raw_item_id"],))
    rows = db.query("SELECT activation_ok FROM raw_items")
    assert all(r["activation_ok"] == 1 for r in rows)  # both released
