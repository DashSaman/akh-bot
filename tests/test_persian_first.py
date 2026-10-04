"""§FA-FIRST regressions (owner 2026-10-04): translation must never be the
newsroom bottleneck.

1) A cluster containing ANY Persian claim publishes the Persian version
   immediately — the foreign item remains corroborating evidence and the
   translation queue is bypassed.
2) The pipeline skips the translation path when the built content is
   already Persian, even if the event's configured source language is
   foreign (that path held the entire foreign backlog).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.newsroom.story_evolution import select_headline

_TS = "2030-01-01T00:00:00+00:00"
_NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")


def test_persian_claim_wins_over_foreign_in_same_cluster():
    cluster = [
        {"state": "UNVERIFIED",
         "text": "טיסות החילוץ מדובאי יצאו מחר כמתוכנן\nלמבזק המלא ב-ynet >"},
        {"state": "UNVERIFIED", "text": "ایران: وزیر نفت استعفا داد"},
    ]
    hl = select_headline(cluster)
    assert hl and "وزیر نفت" in hl
    # Persian content check passes -> pipeline will skip translation
    from app.publishing.telegram_bot import is_persian_public_text
    assert is_persian_public_text(hl)


def test_foreign_only_cluster_still_translates():
    cluster = [{"state": "UNVERIFIED",
                "text": "Trilateral talks could happen this month in UAE"}]
    hl = select_headline(cluster)
    assert hl and "Trilateral" in hl  # unchanged fallback behavior
    from app.publishing.telegram_bot import is_persian_public_text
    assert not is_persian_public_text(hl)


def test_persian_claim_at_lower_tier_still_loses_to_confirmed_foreign():
    """Persian-first never overrides VERIFICATION: a CORROBORATED foreign
    claim outranks an UNVERIFIED Persian one (priority != trust)."""
    cluster = [
        {"state": "CORROBORATED", "text": "Ceasefire signed by both parties"},
        {"state": "UNVERIFIED", "text": "ایران: وزیر نفت استعفا داد"},
    ]
    hl = select_headline(cluster)
    assert "Ceasefire" in hl
