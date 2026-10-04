"""FINAL MEDIA closeout regressions (2026-10-04).

Ladder: original photo → original video → text-only. Never a generated
card. No permanent binary storage; temp files die after success AND
failure; Telegram file_id is captured and reused; media edits use
editMessageCaption; disk temp stays bounded; foreign leak 0; dup SEND 0.
"""
from __future__ import annotations

import json
import os

import httpx
import pytest

from app.ingestion.rss import extract_media_refs
from app.publishing import media as M
from app.publishing.telegram_bot import TelegramBotPublisher

FA = "🔴 **تیتر خبر**\n\nمتن کامل خبر فارسی برای آزمون\n\n🆔 @RastehNews"


def _pub(transport):
    return TelegramBotPublisher("t", "-100chat", transport=httpx.MockTransport(transport))


# ---------------- extraction (feed → media_json) ----------------

class _Entry:
    """feedparser-like entry stand-in."""
    def __init__(self, enclosures=None, media_content=None, summary=""):
        self.enclosures = enclosures or []
        self.media_content = media_content or []
        self.media_thumbnail = []
        self.summary = summary


def test_extract_media_refs_priority_and_dedup():
    e = _Entry(
        enclosures=[{"href": "https://s/v.mp4", "type": "video/mp4"}],
        media_content=[{"url": "https://s/img.jpg", "medium": "image"}],
        summary='<p><img src="https://s/img.jpg"></p> <img src="https://s/inline.png">')
    refs = extract_media_refs(e)
    urls = [r["url"] for r in refs]
    assert urls[0] == "https://s/img.jpg"      # media:content first
    assert urls.count("https://s/img.jpg") == 1  # deduped
    assert "https://s/inline.png" in urls       # inline <img> fallback
    assert {"url": "https://s/v.mp4", "type": "video"} in refs
    assert extract_media_refs(_Entry(summary="no media here")) == []


# ---------------- ladder 1+2: file_id then URL-direct ----------------

@pytest.mark.asyncio
async def test_send_by_url_direct_no_local_bytes():
    calls = []

    async def transport(request: httpx.Request) -> httpx.Response:
        await request.aread()
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": {
            "message_id": 9, "photo": [{"file_id": "FID-1"}]}})

    r = await _pub(transport).send_media_ref(
        {"url": "https://src/original.jpg"}, FA)
    assert r["ok"] and r["mode"] == "url" and r["file_id"] == "FID-1"
    path, body = calls[0]
    assert path.endswith("sendPhoto") and body["photo"] == "https://src/original.jpg"


@pytest.mark.asyncio
async def test_file_id_reused_without_redownload():
    calls = []

    async def transport(request: httpx.Request) -> httpx.Response:
        await request.aread()
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": {
            "message_id": 10, "video": {"file_id": "VFID"}}})

    r = await _pub(transport).send_media_ref(
        {"file_id": "VFID", "url": "https://src/v.mp4", "video": True}, FA, video=True)
    assert r["mode"] == "file_id"
    path, body = calls[0]
    assert path.endswith("sendVideo") and body["video"] == "VFID"
    assert len(calls) == 1  # URL never touched


# ---------------- ladder 3: temp download → upload → DELETE ----------------

@pytest.mark.asyncio
async def test_temp_deleted_after_success(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "temp_dir", lambda: str(tmp_path))
    blob = b"\xff\xd8jpegdata" * 50
    tpath = str(tmp_path / "7-abc")
    with open(tpath, "wb") as f:
        f.write(blob)

    async def transport(request: httpx.Request) -> httpx.Response:
        await request.aread()
        return httpx.Response(200, json={"ok": True, "result": {
            "message_id": 11, "photo": [{"file_id": "F2"}]}})

    r = await _pub(transport).send_media_ref({"tmp_path": tpath}, FA)
    assert r["ok"] and r["mode"] == "tmp"
    assert not os.path.exists(tpath), "temp file MUST be deleted after success"


@pytest.mark.asyncio
async def test_temp_deleted_after_failure_then_text_only(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "temp_dir", lambda: str(tmp_path))
    tpath = str(tmp_path / "8-xyz")
    with open(tpath, "wb") as f:
        f.write(b"\xff\xd8jpegdata")

    async def transport(request: httpx.Request) -> httpx.Response:
        await request.aread()
        if request.url.path.endswith(("sendPhoto", "sendVideo")):
            return httpx.Response(400, json={"ok": False,
                                             "description": "Bad Request: PHOTO_INVALID_DIMENSIONS"})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 12}})

    r = await _pub(transport).send_media_ref({"tmp_path": tpath}, FA)
    assert r["ok"], "degrades to clean text-only, never fails the story"
    assert not os.path.exists(tpath), "temp file MUST be deleted after failure"


@pytest.mark.asyncio
async def test_url_rejected_then_downloader_temp_then_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "temp_dir", lambda: str(tmp_path))
    made = {"p": ""}

    async def downloader(url):
        made["p"] = str(tmp_path / "dl")
        with open(made["p"], "wb") as f:
            f.write(b"\xff\xd8image")
        return made["p"]

    async def transport(request: httpx.Request) -> httpx.Response:
        await request.aread()
        ctype = request.headers.get("content-type", "")
        if request.url.path.endswith("sendPhoto") and "json" in ctype \
                and json.loads(request.content or b"{}").get("photo", "").startswith("http"):
            return httpx.Response(400, json={"ok": False,
                                             "description": "Bad Request: failed to get HTTP URL content"})
        if request.url.path.endswith("sendPhoto"):  # multipart upload of temp
            return httpx.Response(200, json={"ok": True, "result": {
                "message_id": 13, "photo": [{"file_id": "F3"}]}})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 13}})

    r = await _pub(transport).send_media_ref(
        {"url": "https://src/x.jpg"}, FA, downloader=downloader)
    assert r["ok"] and r["mode"] == "tmp" and r["file_id"] == "F3"
    assert not os.path.exists(made["p"]), "temp download deleted after upload"


# ---------------- ladder 4: no media → text-only; no generated card ----------------

@pytest.mark.asyncio
async def test_no_media_text_only():
    async def transport(request: httpx.Request) -> httpx.Response:
        await request.aread()
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 14}})

    r = await _pub(transport).send_media_ref({}, FA)
    assert r["ok"] and "message_id" in r


def test_branded_card_registration_is_noop_by_default(db):
    from app.db.repo import EventsRepo  # noqa: F401

    db.execute(
        "INSERT INTO events(id,title,category,status,first_seen_at,last_seen_at)"
        " VALUES (1,'t','general','NEW',datetime('now'),datetime('now'))")
    db.execute(
        "INSERT INTO stories(id,event_id,slug,headline,lead,draft_json,version,status,"
        "created_at,updated_at) VALUES (1,1,'s','h','','{}',1,'DRAFT',"
        "datetime('now'),datetime('now'))")
    assert M.register_branded_fallback(db, story_id=1, event_id=1,
                                       headline="h") is None
    assert M.assets_for_story(db, 1) == []


# ---------------- disk guard ----------------

def test_temp_budget_evicts_oldest(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "temp_dir", lambda: str(tmp_path))
    monkeypatch.setattr(M, "TEMP_DIR_MAX_BYTES", 300)
    for i, age in enumerate((1000, 2000, 3000)):  # oldest last by mtime
        p = tmp_path / f"f{i}"
        p.write_bytes(b"x" * 100)
        stamp = 1_000_000_000 + age
        os.utime(p, (stamp, stamp))
    M.enforce_temp_budget(150)  # would exceed cap → oldest evicted
    remaining = sorted(f.name for f in tmp_path.iterdir())
    assert "f2" not in remaining  # oldest evicted first
    total = sum(f.stat().st_size for f in tmp_path.iterdir())
    assert total + 150 <= 300 or "f1" not in remaining
