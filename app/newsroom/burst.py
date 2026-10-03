"""P3-D — burst aggregation of rapidly arriving fragments (EVENT-003, REG-037).

EVENT_BURST_WINDOW_SECONDS groups rapidly arriving fragments/claims BEFORE any
later publication logic. It is deliberately NOT the per-event-type continuation
window (minutes, owned by the event matcher in event_fingerprint): the
continuation window belongs to event matching / follow-up evidence association,
while the burst window is a short SECONDS window for rapid fragment arrival.
The two windows are independent and never interchangeable.

Grouping is semantic, never time-only (REG-037): same source + within burst
window + (same event_type OR same context_ref OR topic-token overlap) AND no
boundary (second-occurrence marker / hard category switch / explicit speaker
switch). Unrelated rapid messages therefore stay in separate groups; same
interview fragments share one group.

Idempotency (§12): membership is UNIQUE(raw_item_id) — an item belongs to
exactly ONE burst group; replay/short-circuit returns the existing group and
never duplicates rows. Candidate scan is bounded (§39 performance).

Breaking safety: grouping NEVER delays or withholds anything — it only labels
membership. A later high-priority complete claim can publish immediately
(P3-E/F decision) while same-burst fragments keep aggregating/updating it.

P3-D scope: grouping information only. No SEND/EDIT, no StoryVersion, no
materiality, no publication delay policy, no Telegram calls.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.newsroom.event_fingerprint import detect_event_type, detect_second_occurrence, tokens
from app.newsroom.source_context import HARD_BOUNDARY_TYPES, extract_explicit_speaker, _same_speaker

BURST_CANDIDATE_SCAN = 5   # bounded candidate scan (§39 — never O(all-history))

# Persian light verbs / helper words — a shared «شد» is NOT a shared topic
_WEAK_TOKENS = frozenset({
    "شد", "است", "دارد", "بود", "کرد", "شود", "هستند", "باشد", "بوده",
    "می", "و", "را", "این", "آن", "نیز", "هم", "برای",
})


@dataclass
class BurstSignal:
    source_id: int
    text: str
    occurred_at: str                       # ISO-8601 UTC
    event_type: str = ""
    context_ref: str = ""                  # inherited/stored source-context ref
    topic_tokens: frozenset = frozenset()


def make_signal(source_id: int, text: str, occurred_at: str,
                context_ref: str = "") -> BurstSignal:
    return BurstSignal(
        source_id=source_id, text=text or "", occurred_at=occurred_at,
        event_type=detect_event_type(text or ""), context_ref=context_ref,
        topic_tokens=frozenset(tokens(text or "")))


def _parse(ts: str) -> float | None:
    import datetime

    try:
        return datetime.datetime.fromisoformat(ts).timestamp()
    except (TypeError, ValueError):
        return None


def _boundary(prev: BurstSignal, nxt: BurstSignal) -> list[str]:
    """Deterministic boundary signals — any hit forces a separate group."""
    out: list[str] = []
    if detect_second_occurrence(nxt.text):
        out.append("EVENT_BOUNDARY_MARKER")
    if prev.event_type in HARD_BOUNDARY_TYPES and nxt.event_type in HARD_BOUNDARY_TYPES \
            and prev.event_type != nxt.event_type:
        out.append("HARD_CATEGORY_SWITCH")
    sp, sn = extract_explicit_speaker(prev.text), extract_explicit_speaker(nxt.text)
    if sp and sn and not _same_speaker(sp, sn):
        out.append("SPEAKER_SWITCH")
    return out


def _compatibility(prev: BurstSignal, nxt: BurstSignal) -> list[str]:
    reasons: list[str] = []
    if prev.event_type and prev.event_type == nxt.event_type:
        reasons.append("EVENT_TYPE_MATCH")
    if prev.context_ref and prev.context_ref == nxt.context_ref:
        reasons.append("CONTEXT_REF_MATCH")
    if (prev.topic_tokens & nxt.topic_tokens) - _WEAK_TOKENS:
        reasons.append("TOPIC_OVERLAP")
    return reasons


def should_group(prev: BurstSignal, nxt: BurstSignal,
                 window_seconds: int) -> tuple[bool, list[str]]:
    """Pure decision — same source + within window + semantic link + no
    boundary. Fail-closed on unparseable time (never group on a guess)."""
    if prev.source_id != nxt.source_id:
        return False, ["SOURCE_DIFFERS"]
    a, b = _parse(prev.occurred_at), _parse(nxt.occurred_at)
    if a is None or b is None:
        return False, ["TIME_UNPARSEABLE"]
    if abs(b - a) > window_seconds:
        return False, ["WINDOW_EXCEEDED"]
    boundary = _boundary(prev, nxt)
    if boundary:
        return False, boundary
    compat = _compatibility(prev, nxt)
    if compat:
        return True, compat
    return False, ["NO_SEMANTIC_LINK"]


def assign_burst_group(db, signal: BurstSignal, *, raw_item_id: int,
                       window_seconds: int) -> int:
    """Idempotent assignment of one raw item to a burst group.

    Replay/retry: an already-assigned item short-circuits to its existing
    group (UNIQUE(raw_item_id)) — no duplicate memberships. New items attach
    to the most recent compatible group of the same source (bounded scan) or
    open a new group. Deterministic given (source_id, occurred_at, item id)
    processing order.
    """
    existing = db.query_one(
        "SELECT burst_group_id FROM burst_members WHERE raw_item_id=?",
        (raw_item_id,))
    if existing:
        return int(existing["burst_group_id"])

    rows = db.query(
        "SELECT id, event_type, context_ref, speaker, topic_tokens, last_seen_at"
        " FROM burst_groups WHERE source_id=?"
        " ORDER BY last_seen_at DESC, id DESC LIMIT ?",
        (signal.source_id, BURST_CANDIDATE_SCAN))
    for row in rows:
        prev = BurstSignal(
            source_id=signal.source_id, text="", occurred_at=row["last_seen_at"],
            event_type=row["event_type"], context_ref=row["context_ref"],
            topic_tokens=frozenset(json.loads(row["topic_tokens"] or "[]")))
        ok, _ = should_group(prev, signal, window_seconds)
        # speaker-switch boundary needs the group's speaker (rows carry no text)
        if ok:
            gs = row["speaker"]
            sn = extract_explicit_speaker(signal.text)
            if gs and sn and not _same_speaker(gs, sn):
                ok = False
        if ok:
            merged = sorted(set(json.loads(row["topic_tokens"] or "[]"))
                            | set(signal.topic_tokens))
            speaker = row["speaker"] or (extract_explicit_speaker(signal.text) or "")
            with db.tx() as conn:
                conn.execute(
                    "UPDATE burst_groups SET last_seen_at=?, raw_count=raw_count+1,"
                    " topic_tokens=?, speaker=? WHERE id=?",
                    (signal.occurred_at, json.dumps(merged, ensure_ascii=False),
                     speaker, row["id"]))
                conn.execute(
                    "INSERT OR IGNORE INTO burst_members(burst_group_id,"
                    " raw_item_id, created_at) VALUES(?,?,?)",
                    (row["id"], raw_item_id, signal.occurred_at))
            return int(row["id"])

    speaker = extract_explicit_speaker(signal.text) or ""
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO burst_groups(source_id, event_type, context_ref, speaker,"
            " topic_tokens, first_seen_at, last_seen_at, raw_count)"
            " VALUES(?,?,?,?,?,?,?,1)",
            (signal.source_id, signal.event_type, signal.context_ref, speaker,
             json.dumps(sorted(signal.topic_tokens), ensure_ascii=False),
             signal.occurred_at, signal.occurred_at))
        gid = int(cur.lastrowid)
        conn.execute(
            "INSERT OR IGNORE INTO burst_members(burst_group_id, raw_item_id,"
            " created_at) VALUES(?,?,?)", (gid, raw_item_id, signal.occurred_at))
    return gid


def group_items(db, signals: list[tuple[int, BurstSignal]],
                window_seconds: int) -> dict[int, int]:
    """Convenience: assign an ordered list of (raw_item_id, signal) pairs.
    Deterministic — callers MUST pass items in (source_id, occurred_at,
    raw_item_id) order; this function preserves the given order."""
    return {rid: assign_burst_group(db, sig, raw_item_id=rid,
                                    window_seconds=window_seconds)
            for rid, sig in signals}
