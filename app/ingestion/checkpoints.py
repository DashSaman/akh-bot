"""Persistent source checkpoints (PART-2 T1).

Hard rule (§8): a checkpoint advances ONLY after the corresponding item is
durably persisted (or when require_item=False explicitly for catch-up of items
proven present). Checkpoints are monotonic and DB-backed (survive restart).
"""
from __future__ import annotations

from typing import Any


def advance_checkpoint(db, source_id: int, remote_id: int, item_id: int | None = None,
                       remote_ts: str | None = None, require_item: bool = True) -> bool:
    """Persist-then-advance. Returns True iff checkpoint moved forward."""
    row = db.query_one("SELECT last_remote_id, last_processed_item FROM sources WHERE id=?",
                       (source_id,))
    if row is None:
        return False
    current = row["last_remote_id"] or 0
    if remote_id <= current:
        return False  # monotonic: never backwards / never re-claim same
    if require_item:
        if item_id is None:
            return False
        if db.query_one("SELECT 1 FROM raw_items WHERE id=?", (item_id,)) is None:
            return False  # item must be durably persisted before checkpoint moves
    elif item_id is not None and db.query_one(
            "SELECT 1 FROM raw_items WHERE id=?", (item_id,)) is None:
        return False  # even catch-up may not point at a nonexistent item
    db.execute(
        "UPDATE sources SET last_remote_id=?, last_remote_ts=COALESCE(?, last_remote_ts),"
        " last_processed_item=COALESCE(?, last_processed_item) WHERE id=?",
        (remote_id, remote_ts, item_id, source_id))
    return True


def backfill(db) -> int:
    """Idempotent: seed last_remote_id from fetch_state watermark where NULL."""
    import json as _j

    n = 0
    for s in db.query("SELECT id, fetch_state, last_remote_id FROM sources"):
        if s["last_remote_id"] is not None:
            continue
        try:
            wm = _j.loads(s["fetch_state"] or "{}").get("watermark")
        except Exception:
            wm = None
        if wm:
            db.execute("UPDATE sources SET last_remote_id=? WHERE id=?", (int(wm), s["id"]))
            n += 1
    return n


def fetch_window(messages: list[dict[str, Any]], checkpoint: int) -> list[dict[str, Any]]:
    """Overlap window: return only messages strictly newer than the checkpoint.
    Older ones are re-delivered after restarts and are dropped here (dedup by
    external key remains the second net). SOURCE_OVERLAP_SECONDS is honoured by
    the caller requesting slightly more history than the checkpoint."""
    if not checkpoint:
        return list(messages)
    return [m for m in messages if int(m.get("id", 0)) > checkpoint]
