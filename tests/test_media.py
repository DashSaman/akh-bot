"""Media pipeline tests: send_photo/send_video, cache lifecycle, disk guard, platforms."""
import asyncio
import json
import os

import httpx
import pytest

from app.db.repo import EventsRepo, SourcesRepo, StoriesRepo

from app.publishing import media as M
from app.publishing.telegram_bot import TelegramBotPublisher


def _story(db):
    SourcesRepo(db).create(name="s", platform="rss", url="u", status="APPROVED")
    db.execute("INSERT INTO events(title,status,first_seen_at,last_seen_at) VALUES('e','NEW','2030-01-01','2030-01-01')")
    eid = db.query_one("SELECT last_insert_rowid() i")["i"]
    return StoriesRepo(db).create(eid, "تیتر", "لید", {"platform_variants": {"telegram": "متن"}})


def test_send_photo_with_caption(db, tmp_path, monkeypatch):
    calls = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["url"] = str(request.url)
        calls["body"] = request.content[:200]
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 55}})

    img = tmp_path / "x.jpg"
    img.write_bytes(b"\xff\xd8fake")
    pub = TelegramBotPublisher("t", "-1004", transport=httpx.MockTransport(handler))
    r = asyncio.run(pub.send_media(str(img), "🟢 <b>تیتر</b>\n\nمتن\n\nمنبع: نایا"))
    assert r["ok"] and r["message_id"] == 55
    assert "sendPhoto" in calls["url"] and b"parse_mode=HTML" in calls["body"].replace(b"+", b" ") or "caption" in str(calls["body"])
    r2 = asyncio.run(pub.send_media(str(img), "کپشن فارسی ویدیو آزمون", video=True))
    assert "sendVideo" in calls["url"]


def test_media_cache_lifecycle_delete_after_sent(db, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sid = _story(db)
    meta = M.save_temp(b"imagebytes", "jpg", sid)
    M.record(db, sid, meta)
    assert os.path.exists(meta["path"])
    # while nothing SENT: TTL long → retained
    out = M.cleanup_published_and_expired(db, ttl_minutes=60)
    assert os.path.exists(meta["path"])
    # mark SENT → bytes deleted, metadata path removed
    db.execute("INSERT INTO publications(story_id,platform,status,payload_hash,created_at,updated_at)"
               " VALUES(?,?,?,?,datetime('now'),datetime('now'))", (sid, "telegram", "SENT", "h"))
    M.cleanup_published_and_expired(db, ttl_minutes=60)
    assert not os.path.exists(meta["path"])
    assert db.query_one("SELECT COUNT(*) c FROM media_cache")["c"] == 0


def test_ttl_cleanup_orphans(db, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    junk = os.path.join(M.cache_dir(), "partial.bin")
    open(junk, "wb").write(b"x" * 10)
    os.utime(junk, (0, 0))  # ancient
    M.cleanup_published_and_expired(db, ttl_minutes=1)
    assert not os.path.exists(junk)


def test_disk_guard(db, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert M.media_downloads_allowed(db, critical=1) is False  # any real disk >1%
    assert M.media_downloads_allowed(db, critical=100) is True


def test_branded_card(db, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    out = M.branded_card("تیتر آزمون کارت خبری راسته")
    assert out.endswith(".png") and os.path.exists(out)


def test_platform_page_renders_truthful_states(admin_client):
    html = admin_client.get("/admin/platforms").text
    assert "پلتفرم" in html
    assert "telegram" in html and any(st in html for st in ("LIVE", "CONNECTED", "NOT_CONFIGURED"))
    assert "BLOCKED_BY_COST_POLICY" in html          # X: paid API in zero-cost mode
    assert "AUTH_REQUIRED" in html                    # instagram/threads: no OAuth yet
    assert "PAUSED" not in html.split("telegram")[1][:80]  # telegram publishing ON


def test_platform_toggle_persists(admin_client):
    token = admin_client.cookies.get("akh_csrf")
    admin_client.post("/admin/platforms/x/toggle", data={"csrf": token})
    html = admin_client.get("/admin/platforms").text
    assert "توقف انتشار" in html or "OFF" in html
    admin_client.post("/admin/platforms/x/toggle", data={"csrf": token})  # restore


def test_media_page_renders(admin_client):
    html = admin_client.get("/admin/media").text
    assert "مدیا" in html and "MB" in html
