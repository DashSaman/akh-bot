"""PART-6 — canonical MediaAsset truthful labels (CORE-006/MEDIA-003/REG-025)."""
import asyncio

import httpx
import pytest

from app.db.repo import RawItemsRepo, SourcesRepo
from app.newsroom.v2_pipeline import process_new_items_v2
from app.publishing import media as M


def _story(db, sid, eid=1):
    from app.db.repo import EventsRepo, StoriesRepo

    if not db.query_one("SELECT 1 FROM events WHERE id=?", (eid,)):
        EventsRepo(db).create("seed", first_item=None) if False else db.execute(
            "INSERT INTO events(id,title,category,status,first_seen_at,last_seen_at)"
            " VALUES(?, 't','general','NEW',datetime('now'),datetime('now'))", (eid,))
    db.execute(
        "INSERT OR IGNORE INTO stories(id,event_id,slug,headline,lead,draft_json,"
        " version,status,created_at,updated_at) VALUES(?,?,?,?,'', '{}',1,'DRAFT',"
        " datetime('now'),datetime('now'))", (sid, eid, f"s{sid}", f"headline {sid}"))
    return sid



def test_truthful_status_labels(db):
    _story(db, 1)
    a = M.register_asset(db, story_id=1, event_id=1, raw_item_id=None,
                         source_id=1, kind="photo", status="SOURCE_REFERENCE",
                         sha256="ref-abc", remote_url="https://x/y.jpg")
    b = M.register_branded_fallback(db, story_id=1, event_id=1,
                                    headline="تیتر تست", icon="🟢")
    assets = M.assets_for_story(db, 1)
    labels = {x["status"] for x in assets}
    assert labels == {"SOURCE_REFERENCE", "BRANDED_FALLBACK"}
    # fallback card never masquerades as original
    card = next(x for x in assets if x["status"] == "BRANDED_FALLBACK")
    assert card["kind"] == "card" and "truth" not in card["caption_ref"]


def test_checksum_dedup(db):
    _story(db, 1, eid=1)
    _story(db, 2, eid=2)
    M.register_asset(db, story_id=1, event_id=1, raw_item_id=None, source_id=1,
                     kind="photo", status="SOURCE_REFERENCE", sha256="dup-1")
    M.register_asset(db, story_id=2, event_id=2, raw_item_id=None, source_id=2,
                     kind="photo", status="SOURCE_REFERENCE", sha256="dup-1")
    n = db.query_one("SELECT COUNT(*) AS n FROM media_assets")["n"]
    assert n == 1, "same checksum = one canonical asset"


def test_capture_original_success_and_size_limit(db, tmp_path, monkeypatch):
    monkeypatch.setattr(M, "cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr(M, "media_downloads_allowed", lambda db, critical=85: True)
    real_bytes = b"\xff\xd8jpegbytes" * 100

    def handler(request):
        return httpx.Response(200, content=real_bytes,
                              headers={"content-type": "image/jpeg"})

    transport = httpx.MockTransport(handler)
    r = asyncio.run(M.capture_original(db, url="https://src/img.jpg",
                                       story_id=None, event_id=None,
                                       raw_item_id=None, source_id=1,
                                       client_factory=lambda **kw: httpx.AsyncClient(transport=transport, **kw)))
    assert r["status"] == "ORIGINAL_MEDIA" and r["path"]
    # size limit → truthful SOURCE_REFERENCE, never a fake original
    r2 = asyncio.run(M.capture_original(db, url="https://src/big.jpg",
                                        story_id=None, event_id=None,
                                        raw_item_id=None, source_id=1,
                                        max_mb=0.00001,
                                        client_factory=lambda **kw: httpx.AsyncClient(transport=transport, **kw)))
    assert r2["status"] == "SOURCE_REFERENCE" and not r2.get("path")


def test_best_for_story_prefers_original(db, tmp_path, monkeypatch):
    _story(db, 9, eid=9)
    monkeypatch.setattr(M, "cache_dir", lambda: str(tmp_path))
    M.register_asset(db, story_id=9, event_id=9, raw_item_id=None, source_id=1,
                     kind="photo", status="SOURCE_REFERENCE", sha256="r1")
    M.register_branded_fallback(db, story_id=9, event_id=9, headline="h")
    best = M.best_for_story(db, 9)
    assert best["status"] == "BRANDED_FALLBACK"
    M.register_asset(db, story_id=9, event_id=9, raw_item_id=None, source_id=1,
                     kind="photo", status="ORIGINAL_MEDIA", sha256="o1",
                     path="/tmp/x.jpg")
    best2 = M.best_for_story(db, 9)
    assert best2["status"] == "ORIGINAL_MEDIA"


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
    assert "SOURCE_REFERENCE" in labels and "BRANDED_FALLBACK" in labels
    job = db.query_one("SELECT payload_json FROM jobs WHERE job_type='publish_send'")
    import json
    payload = json.loads(job["payload_json"])
    assert payload.get("media_path"), "send job carries the best asset path"
