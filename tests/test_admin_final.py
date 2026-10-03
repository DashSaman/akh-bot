"""PART-7 final admin: manual intake (canonical only) + health dashboard."""
import json

from app.db.repo import RawItemsRepo, SourcesRepo, utcnow
from app.newsroom.v2_pipeline import process_new_items_v2


def test_intake_requires_login(client):
    assert client.get("/admin/intake", follow_redirects=False).status_code == 303


def test_intake_creates_rawitem_in_canonical_pipeline(admin_client):
    csrf = admin_client.cookies.get("akh_csrf", "")
    resp = admin_client.post("/admin/intake", data={
        "csrf": csrf, "text": "بانک مرکزی امروز نرخ بهره را تغییر داد و بازار واکنش نشان داد",
        "url": "https://example.test/news/1", "language": "fa"}, follow_redirects=False)
    assert resp.status_code == 303
    db = admin_client.app.state.db
    item = db.query_one(
        "SELECT * FROM raw_items WHERE external_key LIKE 'manual:%' ORDER BY id DESC")
    assert item and item["activation_ok"] == 1
    # no publication job until the pipeline processes it
    assert db.query_one("SELECT COUNT(*) AS n FROM jobs")["n"] == 0
    # canonical pipeline processes it → story via normal gates (no bypass)
    class B: short_name = "راسته"; name_fa = "راسته"; tagline_fa = "خ"; telegram_handle = "R"

    class S: event_engine_v2_enabled = True; max_public_story_details = 5; edit_debounce_seconds = 120; verifying_deadline_minutes = 60; standard_max_age_minutes = 180
    process_new_items_v2(db, B(), S())
    sends = db.query("SELECT * FROM jobs WHERE job_type='publish_send'")
    assert len(sends) <= 1, "manual input publishes only through normal gates"


def test_health_dashboard_renders(admin_client, db):
    resp = admin_client.get("/admin/health")
    assert resp.status_code == 200
    for token in ("V2", "duplicate-SEND", "NOT_CONFIGURED", "TELETHON_LOGIN"):
        assert token in resp.text
    assert "sk-" not in resp.text and "API_KEY=" not in resp.text


def test_health_requires_login(client):
    assert client.get("/admin/health", follow_redirects=False).status_code == 303
