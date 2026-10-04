"""REGRESSION: a Telegram source added via SourceManager MUST be pollable.

The scheduler dispatches telegram sources only when
source_type='telegram_web_preview' (t.me/s/ collector; this deployment has
no Telethon creds). add_source previously stamped 'direct' — the source
looked healthy but was NEVER fetched (2026-10-04 owner-added channels
silently idle). The identity must also attach on request (same newsroom).
"""
from __future__ import annotations

from app.newsroom.source_manager import SourceManager


def test_added_telegram_source_is_scheduler_pollable(db):
    mgr = SourceManager(db)
    res = mgr.add_source("https://t.me/russiamilitery", actor="t")
    src = res["source"]
    assert src["enabled"] == 1
    assert src["source_type"] == "telegram_web_preview", \
        "scheduler only fetches telegram_web_preview sources"
    assert src["platform"] == "telegram"
    assert src["url"].startswith("https://t.me/s/")


def test_same_newsroom_attaches_requested_identity(db):
    mgr = SourceManager(db)
    mgr.add_source("https://t.me/caronline_original",
                   identity="CarOnline", actor="t")
    res = mgr.add_source("https://t.me/caronline", identity="CarOnline",
                         actor="t")
    assert res["ok"]
    rows = db.query("SELECT identity, source_type FROM sources WHERE url LIKE"
                    " '%caronline%'")
    assert len(rows) == 2
    assert all(r["identity"] == "CarOnline" for r in rows)
    assert all(r["source_type"] == "telegram_web_preview" for r in rows)
