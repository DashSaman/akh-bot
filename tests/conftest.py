"""Shared fixtures: temp SQLite DB + FastAPI TestClient with workers off."""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings  # noqa: E402
from app.db.database import Database  # noqa: E402
from app.db.migrate import apply_migrations  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    """Module-level throttle must not leak between tests."""
    from app.admin import views as admin_views

    admin_views.throttle._failures.clear()
    yield
    admin_views.throttle._failures.clear()


@pytest.fixture()
def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    apply_migrations(database)
    yield database
    database.close()


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        data_dir=str(tmp_path),
        admin_username="admin",
        admin_password="test-pass-123",
        admin_password_hash="",
        session_secret="unit-test-secret",
        workers_enabled=False,
        telegram_bot_token="",
        telegram_staging_chat_id="",
        glm_api_key="",
        public_base_url="https://news.example.test",
        brand_config=str(tmp_path / "brand.yml"),
    )


@pytest.fixture()
def app(settings, db, tmp_path, monkeypatch):
    # point the app at the temp DB before create_app opens its own
    import app.main as main_mod

    brand_path = tmp_path / "brand.yml"
    brand_path.write_text("brand_status: UNDECIDED\nname_fa: تست\nshort_name: تست\n", encoding="utf-8")
    settings = settings.model_copy(update={"brand_config": str(brand_path)})

    opened = {}

    class FakeDb(Database):
        def __init__(self, path):  # reuse migrated fixture db
            self.path = path
            import sqlite3, threading

            self._conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=30000")
            self._lock = threading.RLock()
            opened["db"] = self

    monkeypatch.setattr(main_mod, "Database", lambda path: FakeDb(path))
    application = main_mod.create_app(settings)
    application.state.db = opened["db"]
    yield application


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_client(client):
    """Logged-in client with CSRF cookie."""
    csrf = client.cookies.get("akh_csrf") or client.get("/admin/login").cookies.get("akh_csrf")
    resp = client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-pass-123", "csrf": csrf},
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    return client
