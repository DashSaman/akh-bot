"""Cheap-first duplicate detection (stages 1-4) and event clustering.

Stage 5+ (embeddings / LLM comparison) is intentionally deferred — only ambiguous
candidates would ever go there, and none are produced by the current pipeline.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.simhash import likely_near_duplicate, simhash64
from app.core.textnorm import canonical_url, content_hash, title_hash
from app.db.repo import EventsRepo, RawItemsRepo


def fingerprints_for(url: str, title: str, text: str) -> dict[str, str]:
    canon = canonical_url(url)
    # content identity is the BODY (titles legitimately vary between outlets
    # for the same story; headline equality is the separate stage-3 signal)
    return {
        "canonical_url": canon,
        "canonical_url_hash": content_hash(canon) if canon else "",
        "content_hash": content_hash(text),
        "title_norm_hash": title_hash(title),
        "simhash": f"{simhash64(text):016x}",
    }


class DedupResult:
    def __init__(self, is_duplicate: bool, matched_item_id: int | None, stage: str) -> None:
        self.is_duplicate = is_duplicate
        self.matched_item_id = matched_item_id
        self.stage = stage


def classify_duplicate(items: RawItemsRepo, fp: dict[str, str], text: str,
                       exclude_item_id: int | None = None) -> DedupResult:
    # Stage 1: canonical URL
    if fp.get("canonical_url_hash"):
        hits = items.find_by_fingerprint(canonical_url_hash=fp["canonical_url_hash"],
                                         exclude_item_id=exclude_item_id)
        if hits:
            return DedupResult(True, hits[0]["id"], "url")
    # Stage 2: exact content hash
    hits = items.find_by_fingerprint(content_hash=fp["content_hash"],
                                     exclude_item_id=exclude_item_id)
    if hits:
        return DedupResult(True, hits[0]["id"], "content_hash")
    # Stage 3: normalized title (only a strong signal for news headlines)
    if fp.get("title_norm_hash"):
        hits = items.find_by_fingerprint(title_norm_hash=fp["title_norm_hash"],
                                         exclude_item_id=exclude_item_id)
        if hits:
            return DedupResult(True, hits[0]["id"], "title")
    # Stage 4: SimHash near-duplicate against recent window
    if fp.get("simhash"):
        new_sh = int(fp["simhash"], 16)
        for row in items.recent_with_simhash(limit=300, exclude_item_id=exclude_item_id):
            try:
                old_sh = int(row["simhash"], 16)
            except (TypeError, ValueError):
                continue
            if likely_near_duplicate(new_sh, old_sh):
                return DedupResult(True, row["id"], "simhash")
    return DedupResult(False, None, "new")


def find_or_create_event(events: EventsRepo, items: RawItemsRepo, item: dict[str, Any],
                         dup: DedupResult, window_hours: int = 48) -> int:
    """Attach to the existing event of the matched item (within window); else new event."""
    if dup.matched_item_id:
        row = events.db.query_one(
            "SELECT e.* FROM events e JOIN event_items ei ON ei.event_id=e.id WHERE ei.raw_item_id=?"
            " ORDER BY e.id DESC LIMIT 1",
            (dup.matched_item_id,),
        )
        if row:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
            try:
                still_fresh = datetime.fromisoformat(row["last_seen_at"]) >= cutoff
            except (TypeError, ValueError):
                still_fresh = False
            if still_fresh:
                events.attach(row["id"], item["id"], is_duplicate=dup.is_duplicate)
                return row["id"]
            # same wording much later → separate occurrence; falls through to a new event
    return events.create(item["title"] or "(بدون عنوان)", first_item=item)
