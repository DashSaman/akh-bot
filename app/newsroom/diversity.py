"""Soft publication-diversity guard + source-share metrics.

Anti-monopoly, NOT censorship: a story is deferred only when its canonical
source identity would exceed the rolling-hour share caps AND other identities
have publishable stories waiting. Genuinely unique breaking news (P0 weight
or a breaking-flagged source) always passes. Deferral leaves the story/event
untouched so the next pipeline pass retries it — nothing is ever dropped.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

SINGLE_SHARE_CAP = 0.25   # one canonical identity, rolling hour
TOP_TWO_SHARE_CAP = 0.45  # top two identities combined, rolling hour
BREAKING_WEIGHT = 88      # P0 topics (war/internet/currency/diplomacy/iran)
MIN_SAMPLE = 4            # too few posts in the hour to judge fairness
DOMINANT_SHARE = 0.30     # only identities at/above this share get deferred

_IDENT_SQL = (
    "SELECT DISTINCT COALESCE(NULLIF(s.identity, ''), s.name) AS ident"
    " FROM event_items ei"
    " JOIN raw_items ri ON ri.id = ei.raw_item_id"
    " JOIN sources s ON s.id = ri.source_id"
    " WHERE ei.event_id = ?"
)
_BREAKING_SQL = (
    "SELECT COUNT(*) AS c FROM event_items ei"
    " JOIN raw_items ri ON ri.id = ei.raw_item_id"
    " JOIN sources s ON s.id = ri.source_id"
    " WHERE ei.event_id = ? AND s.breaking_source = 1"
)


def story_source_identities(db, event_id: int) -> set[str]:
    return {str(r["ident"]) for r in db.query(_IDENT_SQL, (event_id,))}


def _is_breaking_source(db, event_id: int) -> bool:
    row = db.query_one(_BREAKING_SQL, (event_id,))
    return bool(row and row["c"] > 0)


def hourly_identity_shares(db, since_iso: str) -> Counter:
    """First-SENT publications in the window, counted per canonical identity.

    created_at filter = NEW channel messages only (edits never inflate it).
    """
    rows = db.query(
        "SELECT DISTINCT p.story_id FROM publications p WHERE p.status='SENT'"
        " AND p.created_at>=? AND NOT EXISTS ("
        "  SELECT 1 FROM publications q WHERE q.story_id=p.story_id"
        "  AND q.status='SENT' AND q.id<p.id)",
        (since_iso,))
    shares: Counter[str] = Counter()
    for r in rows:
        ev = db.query_one("SELECT event_id FROM stories WHERE id=?", (r["story_id"],))
        if not ev:
            continue
        for ident in story_source_identities(db, ev["event_id"]):
            shares[ident] += 1
    return shares


def defer_for_diversity(db, event_id: int, weight: int, *,
                        alternatives_ready: int = 0,
                        now_iso: str = "") -> bool:
    """True → skip enqueue THIS pass (soft fairness), retried next pass.

    Never defers: breaking-weight stories, breaking-flagged sources, or when
    no alternative identities have publishable stories waiting.
    """
    if weight >= BREAKING_WEIGHT or _is_breaking_source(db, event_id):
        return False
    idents = story_source_identities(db, event_id)
    if not idents:
        return False
    since = (now_iso or _now_hour_iso())
    shares = hourly_identity_shares(db, since)
    total = sum(shares.values())
    if total < MIN_SAMPLE:
        return False
    if alternatives_ready <= 0:
        return False
    # Only a genuinely DOMINANT identity is deferred: being over the cap must
    # come with an already-dominant share — a minority voice near the cap is
    # never pushed out (that would worsen the mix it is meant to diversify).
    for ident in idents:
        share_now = shares[ident] / total if total else 0.0
        if share_now >= DOMINANT_SHARE and (
                shares[ident] + 1) > SINGLE_SHARE_CAP * (total + 1):
            return True
    # top-two combined cap is meaningful only with 3+ active identities
    if len(shares) >= 3:
        top_two = [i for i, _ in shares.most_common(2)]
        mine = max(shares, key=lambda i: shares.get(i, 0) if i in idents else -1)
        if any(i in idents for i in top_two):
            combined = sum(c for _, c in shares.most_common(2))
            if combined + 1 > TOP_TWO_SHARE_CAP * (total + 1):
                return True
    return False


def _now_hour_iso() -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(hours=1)) \
        .isoformat(timespec="seconds")


def diversity_metrics(db, *, hours: int = 1) -> dict[str, Any]:
    """Watchdog/admin view: shares + uniqueness for the rolling window."""
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)) \
        .isoformat(timespec="seconds")
    shares = hourly_identity_shares(db, since)
    total = sum(shares.values())
    top = [{"identity": i, "posts": c,
            "share": round(c / total, 3) if total else 0.0}
           for i, c in shares.most_common(5)]
    return {"window_hours": hours, "total_new_posts": total,
            "unique_identities": len(shares), "top": top}
