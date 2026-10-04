"""FINAL MEDIA policy — truthful labels, no generated cards, metadata-only
storage with Telegram file_id reuse (CORE-006/MEDIA-003/REG-025)."""
import asyncio
import json

import httpx
import pytest

from app.db.repo import RawItemsRepo, SourcesRepo
from app.newsroom.v2_pipeline import process_new_items_v2
from app.publishing import media as M


def _story(db, sid, eid=1):
    db.execute(
        "INSERT INTO events(id,title,category,status,first_seen_at,last_seen_at)"
        " VALUES(?, 't','general','NEW',datetime('now'),datetime('now'))", (eid,))
    db.execute(
        "INSERT OR IGNORE INTO stories(id,event_id,slug,headline,lead,draft_json,"
        " version,status,created_at,updated_at) VALUES(?,?,?,?,'', '{}',1,'DRAFT',"
        " datetime('now'),datetime('now'))", (sid, eid, f"s{sid}", f"headline {sid}"))
    return sid


def test_truthful_status_labels_and_retired_cards(db):
    _story(db, 1)
    a = M.register_asset(db, story_id=1, event_id=1, raw_item_id=None,
                         source_id=1, kind="photo", status="SOURCE_REFERENCE",
                         sha256="ref-abc", remote_url="https://x/y.jpg")
    assert a
    # FINAL MEDIA: generated branded cards are RETIRED — registration is a
    # no-op with the production flag off (default).
    assert M.register_branded_fallback(db, story_id=1, event_id=1,
                                       headline="تیتر تست", icon="🟢") is None
    assets = M.assets_for_story(db, 1)
    assert {x["status"] for x in assets} == {"SOURCE_REFERENCE"}


def test_checksum_dedup(db):
    _story(db, 1, eid=1)
    _story(db, 2, eid=2)
    M.register_asset(db, story_id=1, event_id=1, raw_item_id=None, source_id=1,
                     kind="photo", status="SOURCE_REFERENCE", sha256="dup-1",
                     remote_url="https://a/1.jpg")
    M.register_asset(db, story_id=2, event_id=2, raw_item_id=None, source_id=2,
                     kind="photo", status="SOURCE_REFERENCE", sha256="dup-1",
                     remote_url="https://a/1.jpg")
    n = db.query_one("SELECT COUNT(*) AS n FROM media_assets")["n"]
    assert n == 1, "same checksum = one canonical asset"


def test_download_to_temp_success_size_and_deletion(db, tmp_path, monkeypatch):
    monkeypatch.setattr(M, "temp_dir", lambda: str(tmp_path))
    monkeypatch.setattr(M, "media_downloads_allowed", lambda db, critical=85: True)
    real_bytes = b"\xff\xd8jpegbytes" * 100

    def handler(request):
        return httpx.Response(200, content=real_bytes,
                              headers={"content-type": "image/jpeg"})

    transport = httpx.MockTransport(handler)
    factory = lambda **kw: httpx.AsyncClient(transport=transport, **kw)
    path = asyncio.run(M.download_to_temp("https://src/img.jpg", 7, client_factory=factory))
    assert path and path.startswith(str(tmp_path))
    import os
    assert os.path.exists(path)
    os.unlink(path)
    # size limit → no temp file, caller falls through (text-only), never a fake
    path2 = asyncio.run(M.download_to_temp("https://src/img.jpg", 7, max_bytes=10,
                                           client_factory=factory))
    assert path2 == ""
    # HTTP error → ""
    def err_handler(request):
        return httpx.Response(403)
    p3 = asyncio.run(M.download_to_temp("https://src/403.jpg", 7,
                                        client_factory=lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(err_handler), **kw)))
    assert p3 == ""


def test_best_for_story_ladder_and_no_cards(db):
    _story(db, 9, eid=9)
    # URL-only reference is publishable (URL-direct send)
    M.register_asset(db, story_id=9, event_id=9, raw_item_id=None, source_id=1,
                     kind="photo", status="SOURCE_REFERENCE", sha256="r1",
                     remote_url="https://src/photo.jpg")
    best = M.best_for_story(db, 9)
    assert best["status"] == "SOURCE_REFERENCE" and best["remote_url"].endswith(".jpg")
    # ORIGINAL with telegram file_id wins
    M.register_asset(db, story_id=9, event_id=9, raw_item_id=None, source_id=1,
                     kind="photo", status="ORIGINAL_MEDIA", sha256="o1",
                     remote_url="https://src/o.jpg", telegram_file_id="AgACfile1")
    best2 = M.best_for_story(db, 9)
    assert best2["sha256"] == "o1" and best2["telegram_file_id"] == "AgACfile1"
    # photo preferred over video at equal rank
    M.register_asset(db, story_id=9, event_id=9, raw_item_id=None, source_id=1,
                     kind="video", status="ORIGINAL_MEDIA", sha256="v1",
                     remote_url="https://src/v.mp4", telegram_file_id="AgACfile2")
    best3 = M.best_for_story(db, 9)
    assert best3["kind"] == "photo"
    # a BRANDED_FALLBACK row can never be chosen
    M.register_asset(db, story_id=9, event_id=9, raw_item_id=None, source_id=0,
                     kind="card", status="BRANDED_FALLBACK", sha256="c1", path="/x.png")
    assert M.best_for_story(db, 9)["status"] != "BRANDED_FALLBACK"
    # set_telegram_file_id persists
    M.set_telegram_file_id(db, best["id"], "fid-new")
    assert db.query_one("SELECT telegram_file_id f FROM media_assets WHERE id=?",
                        (best["id"],))["f"] == "fid-new"


def test_v2_publish_attaches_media_payload(db, settings):
    s = settings.model_copy(update={"event_engine_v2_enabled": True})
    sid = SourcesRepo(db).create(name="src", platform="telegram",
                                 url="t.me/x", status="APPROVED")
    SourcesRepo(db).update(sid, source_control_state="OWNER_ENABLED")
    RawItemsRepo(db).insert(source_id=sid, platform="telegram", external_key="m1",
                            title="", text="دلار امروز در بازار آزاد به کانال تازه رسید",
                            activation_ok=True, media=[{"url": "https://t.me/i/1.jpg"}],
                            published_at="2026-10-03T10:00:00+00:00")

    class B: short_name = "راسته"; name_fa = "راسته"; tagline_fa = "خ"; telegram_handle = "R"

    class S: event_engine_v2_enabled = True; max_public_story_details = 5; edit_debounce_seconds = 120; verifying_deadline_minutes = 60; standard_max_age_minutes = 180
    process_new_items_v2(db, B(), S())
    story = db.query_one("SELECT * FROM stories")
    assert story, "story created"
    assets = M.assets_for_story(db, story["id"])
    labels = {a["status"] for a in assets}
    assert "SOURCE_REFERENCE" in labels and "BRANDED_FALLBACK" not in labels
    job = db.query_one("SELECT payload_json FROM jobs WHERE job_type='publish_send'")
    payload = json.loads(job["payload_json"])
    assert not payload.get("media_path"), "no frozen media path in payload"
