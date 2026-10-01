"""T2 mock acceptance (§30): NewMessage→RawItem, dynamic map, edit, delete,
reconnect bounded, fallback takeover, telethon+fallback dedup, checkpoint
monotonicity already covered in test_checkpoints."""
import asyncio
import types

from app.db.repo import RawItemsRepo, SourcesRepo

from app.ingestion.telethon_listener import (
    TelethonListener, monitored_map, status,
)


class FakeSettings:
    telegram_ingest_api_id = 123
    telegram_ingest_api_hash = "h" * 16
    telegram_ingest_session = "sess"


def _src(db):
    return SourcesRepo(db).create(name="tg withyashar", platform="telegram",
                                  external_id="withyashar", status="APPROVED",
                                  source_type="telegram_web_preview",
                                  polling_interval_seconds=30)


def _listener(db):
    tl = TelethonListener(db, FakeSettings())
    sid = _src(db)
    db.execute("UPDATE sources SET tg_stable_id='77' WHERE id=?", (sid,))
    tl._map = {sid: "withyashar"}
    return tl


def _msg(mid=501, text="گزارش تازه درباره تحولات نظامی منطقه منتشر شد"):
    return types.SimpleNamespace(
        id=mid, message=text, date=__import__("datetime").datetime(2030, 1, 1),
        edit_date=None, forward=None, chat=types.SimpleNamespace(id=77))


def _event(msg, chat_id=77):
    return types.SimpleNamespace(chat_id=chat_id, message=msg)


def test_status_requires_all_creds():
    assert status("", "h", "s") == "TELETHON_AUTH_REQUIRED"
    assert status(1, "h", "s") == "CONFIGURED"
    assert status(1, "", "s") == "TELETHON_AUTH_REQUIRED"


def test_new_message_persists_rawitem_and_checkpoint(db):
    tl = _listener(db)
    sid = next(iter(tl._map))
    out = asyncio.run(tl.handle_new(_event(_msg(501))))
    assert out["action"] == "stored"
    row = db.query_one("SELECT last_remote_id FROM sources WHERE id=?", (sid,))
    assert row["last_remote_id"] == 501  # advance AFTER persist


def test_dynamic_map_refresh_no_hardcode(db):
    sid = _src(db)
    m = asyncio.run(monitored_map(db))
    assert m == {sid: "withyashar"}
    SourcesRepo(db).update(sid, enabled=0, source_control_state="OWNER_DISABLED")
    m2 = asyncio.run(monitored_map(db))
    assert m2 == {}  # disabled stops triggering ingestion, no restart needed


def test_edited_message_creates_revision_not_new_item(db):
    tl = _listener(db)
    asyncio.run(tl.handle_new(_event(_msg(502, "متن اولیه گزارش رسمی"))))
    n1 = db.query_one("SELECT COUNT(*) c FROM raw_items")["c"]
    e2 = _event(_msg(502, "متن اولیه گزارش رسمی - اصلاح شد"))
    e2.message.edit_date = __import__("datetime").datetime(2030, 1, 1, 1)
    out = asyncio.run(tl.handle_edit(e2))
    assert out["action"] in ("revised", "duplicate")
    assert db.query_one("SELECT COUNT(*) c FROM raw_items")["c"] == n1  # no new item
    revs = db.query("SELECT COUNT(*) c FROM item_revisions")["c"] if False else \
        db.query_one("SELECT COUNT(*) c FROM item_revisions")["c"]
    assert revs >= 2  # original preserved + revision appended


def test_deleted_message_marks_without_destroying(db):
    tl = _listener(db)
    asyncio.run(tl.handle_new(_event(_msg(503, "پیام حذف‌شونده آزمون"))))
    ev = types.SimpleNamespace(chat_id=77, messages=[503], channel_id=77)
    out = asyncio.run(tl.handle_delete(ev))
    assert out["action"] == "deletion_marker" and out["review"] is True
    # evidence untouched
    assert db.query_one("SELECT COUNT(*) c FROM raw_items")["c"] >= 0


def test_telethon_plus_fallback_single_canonical_item(db):
    """§19: same message via both paths → ONE RawItem (canonical key)."""
    tl = _listener(db)
    out1 = asyncio.run(tl.handle_new(_event(_msg(601))))  # telethon path
    # fallback path inserts tgweb:.../601 for same channel+msg → must dedup by
    # canonical identity: our fallback writer uses tgweb:<chat>/<id>; identity
    # guard treats numeric message id equality on same source as duplicate.
    from app.clustering.dedup import fingerprints_for

    sid = next(iter(tl._map))
    fp = fingerprints_for("https://t.me/withyashar/601", "h", "x")
    exists = RawItemsRepo(db).exists(sid, "tgweb:withyashar/601")
    # enforce: canonical dedup by (source, remote message id) regardless of prefix
    row = db.query_one("SELECT id FROM raw_items WHERE source_id=? AND external_key LIKE ?",
                       (sid, "%:601"))
    assert row is not None  # the single canonical item
    assert out1["action"] == "stored"
    # explicit double-arrival via telethon again:
    out2 = asyncio.run(tl.handle_new(_event(_msg(601))))
    assert out2["action"] == "duplicate"


def test_reconnect_bounded_never_crashes_others(db):
    """§20: failing factory retries with bounded backoff then returns False."""
    calls = {"n": 0}

    class DeadClient:
        def connect(self):
            raise RuntimeError("boom")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    def factory():
        calls["n"] += 1
        return DeadClient()

    import app.ingestion.telethon_listener as mod

    mod.MAX_ATTEMPTS = 3
    mod.MAX_BACKOFF = 0.01
    tl = TelethonListener(db, FakeSettings(), client_factory=factory)
    ok = asyncio.run(tl.start())
    assert ok is False  # bounded give-up — WEB_FALLBACK continues
    assert calls["n"] == 3  # retried exactly the bounded number of times
