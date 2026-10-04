"""Self-service source management regressions (§SRC directive).

Dynamic DB-driven registry (no restart), SSRF guard, duplicate/canonical
protection, priority != trust, permission enforcement, publish-time source
state gate, safe test probe, audit trail, historical data survival.
"""
from __future__ import annotations

import pytest

from app.newsroom.source_manager import SourceManager
from app.db.repo import AuditRepo

_TS = "2030-01-01T00:00:00+00:00"


@pytest.fixture()
def mgr(db):
    return SourceManager(db)


# ----------------------------------------------------------- normalization
def test_malformed_and_private_urls_rejected(mgr):
    for bad in ("file:///etc/passwd", "ftp://x.com/f",
                "http://localhost/admin", "http://127.0.0.1:8307/health",
                "http://169.254.169.254/latest", "http://10.0.0.5/feed",
                "not a url", ""):
        assert mgr.normalize(bad) is None, bad
    assert mgr.normalize("https://192.168.1.10/rss") is None  # RFC1918


def test_telegram_and_rss_normalize(mgr):
    tg = mgr.normalize("@caronline_original")
    assert tg == {"platform": "telegram",
                  "external_id": "caronline_original",
                  "url": "https://t.me/s/caronline_original"}
    assert mgr.normalize("https://t.me/example")["platform"] == "telegram"
    assert mgr.normalize("https://ex.com/rss.xml")["platform"] == "rss"
    assert mgr.normalize("https://ex.com/news")["platform"] == "website"


# ------------------------------------------------------------- add / dedup
def test_owner_adds_telegram_source(mgr, db):
    res = mgr.add_source("@caronline_original", display_name="CarOnline",
                         actor="owner")
    assert res["ok"] and res["status"] == "APPROVED"
    src = res["source"]
    assert src["enabled"] == 1 and src["source_control_state"] == "OWNER_ENABLED"
    assert src["name"] == "CarOnline" and src["identity"]
    # trust unchanged: new source starts with independent-count allowed but
    # verification_allowed defaults — owner priority NEVER flips trust itself
    assert src["verification_allowed"] == 1


def test_duplicate_url_rejected_merged(mgr, db):
    mgr.add_source("https://t.me/dupcheck", actor="owner")
    res2 = mgr.add_source("https://t.me/dupcheck", actor="owner")
    assert res2["status"] == "EXISTS"
    assert db.query_one("SELECT COUNT(*) c FROM sources WHERE url LIKE"
                        " '%dupcheck%'")["c"] == 1


def test_same_identity_multiple_endpoints_one_source(mgr, db):
    mgr.add_source("https://t.me/canon_news", identity="CanonNews", actor="o")
    mgr.add_source("https://canonnews.com", identity="CanonNews", actor="o")
    mgr.add_source("https://canonnews.com/rss.xml", identity="CanonNews",
                   actor="o")
    rows = db.query("SELECT * FROM sources WHERE identity='CanonNews'")
    assert len(rows) == 3
    assert len({r["platform"] for r in rows}) == 3  # tg + website + rss
    # all attached to the SAME canonical identity → one corroboration origin


def test_audit_trail_records_changes(mgr, db):
    res = mgr.add_source("https://t.me/auditme", actor="owner")
    mgr.set_enabled(res["source"]["id"], False, actor="owner")
    mgr.set_enabled(res["source"]["id"], True, actor="owner")
    rows = AuditRepo(db).recent(10)
    actions = [r["action"] for r in rows]
    assert "add_source" in actions and "disable_source" in actions \
        and "enable_source" in actions


# --------------------------------------------------- dynamic, no restart
def test_enable_disable_take_effect_immediately(mgr, db):
    res = mgr.add_source("https://t.me/dynsrc", actor="o")
    sid = res["source"]["id"]
    assert mgr.set_enabled(sid, False, actor="o")
    row = db.query_one("SELECT enabled, source_control_state FROM sources"
                       " WHERE id=?", (sid,))
    assert row["enabled"] == 0 and row["source_control_state"] == "OWNER_DISABLED"
    # state is read fresh from the DB — no restart, no cache
    mgr.set_enabled(sid, True, actor="o")
    assert db.query_one("SELECT enabled FROM sources WHERE id=?",
                        (sid,))["enabled"] == 1


def test_disabled_source_cannot_publish_queued_job(db):
    db.execute(
        "INSERT INTO sources (name, platform, external_id, url, language,"
        " category, source_type, status, enabled, priority, notes,"
        " created_at, identity, publication_policy) VALUES ('off', 'telegram',"
        " 'off', 'https://t.me/off', 'fa', '', 'direct', 'APPROVED', 0, 50,"
        " '', ?, 'OffSrc', 'AUTO')", (_TS,))
    sid = db.query_one("SELECT id FROM sources WHERE identity='OffSrc'")["id"]
    assert SourceManager.can_publish_now(db, sid) is False
    db.execute("UPDATE sources SET enabled=1 WHERE id=?", (sid,))
    assert SourceManager.can_publish_now(db, sid) is True
    # STORE_ONLY policy = never publishes
    db.execute("UPDATE sources SET publication_policy='DISCOVERY_ONLY' WHERE id=?",
               (sid,))
    assert SourceManager.can_publish_now(db, sid) is False


# ------------------------------------------------------- priority != trust
def test_priority_change_never_touches_trust(mgr, db):
    res = mgr.add_source("https://t.me/prisrc", actor="o")
    sid = res["source"]["id"]
    before = db.query_one("SELECT verification_allowed,"
                          " can_increase_independent_count FROM sources"
                          " WHERE id=?", (sid,))
    mgr.update_source(sid, "owner", priority=10, polling_tier="VERY_HIGH")
    after = db.query_one("SELECT verification_allowed,"
                         " can_increase_independent_count, priority,"
                         " polling_tier, polling_interval_seconds FROM sources"
                         " WHERE id=?", (sid,))
    assert after["priority"] == 10 and after["polling_tier"] == "VERY_HIGH"
    assert after["verification_allowed"] == before["verification_allowed"]
    assert after["can_increase_independent_count"] == \
        before["can_increase_independent_count"]
    assert after["polling_interval_seconds"] == 60  # VERY_HIGH is faster


def test_archive_preserves_history(mgr, db):
    db.execute(
        "INSERT INTO sources (name, platform, external_id, url, language,"
        " category, source_type, status, enabled, priority, notes,"
        " created_at, identity) VALUES ('arch', 'rss', 'arch',"
        " 'https://arch.example.com/feed', 'fa', '', 'direct', 'APPROVED',"
        " 1, 50, '', ?, 'ArchSrc')", (_TS,))
    sid = db.query_one("SELECT id FROM sources WHERE identity='ArchSrc'")["id"]
    db.execute(
        "INSERT INTO raw_items (source_id, platform, external_key, url, title,"
        " text, language, fetched_at, activation_ok, processed_state)"
        " VALUES (?, 'rss', 'k1', '', 'خبر تاریخی', '', 'fa', ?, 1,"
        " 'PROCESSED')", (sid, _TS))
    mgr.update_source(sid, "owner", status="BLOCKED")
    row = db.query_one("SELECT status, enabled FROM sources WHERE id=?", (sid,))
    assert row["status"] == "BLOCKED" and row["enabled"] == 0
    assert db.query_one("SELECT COUNT(*) c FROM raw_items WHERE source_id=?",
                        (sid,))["c"] == 1  # historical evidence intact


# ------------------------------------------------------------ bot commands
class _Rec:
    def __init__(self):
        self.calls = []

    async def __call__(self, method, payload):
        self.calls.append((method, payload))
        if method == "sendMessage":
            return {"ok": True, "result": {"message_id": 9}}
        return {"ok": True}


@pytest.mark.asyncio
async def test_bot_addsource_and_permissions(db, settings):
    from app.editorial.intake import EditorialIntake
    db.execute(
        "INSERT INTO bot_admins (telegram_user_id, display_name, role, enabled,"
        " can_manage_sources, created_at, updated_at)"
        " VALUES ('80001', 'ادیتور', 'EDITOR', 1, 0, ?, ?)", (_TS, _TS))
    wk = EditorialIntake(db, settings)
    rec = _Rec()
    wk._api = rec
    # editor WITHOUT can_manage_sources → denied
    await wk._dispatch({"message": {"message_id": 1, "chat": {"id": 42},
                                    "from": {"id": 80001},
                                    "text": "/addsource https://t.me/x1",
                                    "date": 1}})
    assert any("مجوز مدیریت منبع" in str(p.get("text"))
               for _, p in rec.calls)
    # grant the permission → works
    db.execute("UPDATE bot_admins SET can_manage_sources=1"
               " WHERE telegram_user_id='80001'")
    await wk._dispatch({"message": {"message_id": 2, "chat": {"id": 42},
                                    "from": {"id": 80001},
                                    "text": "/addsource @caronline_original",
                                    "date": 1}})
    texts = [str(p.get("text")) for m, p in rec.calls if m == "sendMessage"]
    assert any("منبع اضافه شد" in t for t in texts)
    assert db.query_one("SELECT COUNT(*) c FROM sources WHERE url LIKE"
                        " '%caronline_original%'")["c"] >= 1
    # OWNER always allowed (role-based, no explicit flag needed)
    db.execute(
        "INSERT OR IGNORE INTO bot_admins (telegram_user_id, display_name,"
        " role, enabled, can_submit, can_publish, can_edit, can_cancel,"
        " can_manage_admins, created_at, updated_at)"
        " VALUES ('5504556066', 'Owner', 'OWNER', 1, 1, 1, 1, 1, 1, ?, ?)",
        (_TS, _TS))
    await wk._dispatch({"message": {"message_id": 3, "chat": {"id": 42},
                                    "from": {"id": 5504556066},
                                    "text": "/addsource https://t.me/ownsrc",
                                    "date": 1}})
    assert db.query_one("SELECT COUNT(*) c FROM sources WHERE url LIKE"
                        " '%ownsrc%'")["c"] == 1


# ---------------------------------------------------------- test probe
def test_testsource_is_read_only(db):
    db.execute(
        "INSERT INTO sources (name, platform, external_id, url, language,"
        " category, source_type, status, enabled, priority, notes,"
        " created_at, identity) VALUES ('probe', 'rss', 'probe',"
        " 'https://no-such-host-audit.invalid/rss', 'fa', '', 'direct',"
        " 'APPROVED', 1, 50, '', ?, 'ProbeSrc')", (_TS,))
    sid = db.query_one("SELECT id FROM sources WHERE identity='ProbeSrc'")["id"]
    mgr = SourceManager(db)
    res = mgr.test_source(sid)
    assert res["ok"] is False  # unreachable reported truthfully
    assert db.query_one("SELECT COUNT(*) c FROM raw_items WHERE source_id=?",
                        (sid,))["c"] == 0  # probe never ingests/publishes
