"""P3-D — bounded per-source context inheritance (EVENT-003, REG-039, REG-031).

A CONTEXT_ONLY prefix RawItem («ترامپ به مجله تایم:», «نتانیاهو:», «فوری:»,
«منابع عبری:») may provide bounded context (speaker / interview reference /
topic hint) to following compatible COMPLETE items from the SAME source.

Hard bounds (never global, never cross-source):
- ONE live context row per source — schema-enforced UNIQUE(source_id), upsert
- TTL: SOURCE_CONTEXT_TTL_SECONDS — an expired context is dead, never inherited
- inheritance requires: same source + within TTL + compatible topic/category
  + no explicit new-speaker / event / topic boundary (§18)
- reset on: explicit new speaker / event-boundary marker / hard category
  switch / clear topic change / TTL expiry / large time gap (§19)
- persistence is DB-owned (source_context table): survives safe worker
  restart; no hidden process state

RawItems are NEVER dropped or rewritten (INV-002): a prefix alone yields
0 claims / 0 events / 0 stories / 0 publications (REG-031, GATE-03
CONTEXT_ONLY, publishable=False). This module writes ONLY its own bounded
context rows — it never mutates items, claims, events or stories.

P3-D scope: context/grouping information only. No SEND/EDIT, no StoryVersion,
no materiality, no publication delay, no Telegram calls (P3-E/P3-F own those).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.newsroom.claim_model import (
    _MIN_MEANINGFUL_TOKENS, ClaimClass, detect_class, is_prefix_fragment,
    normalize,
)
from app.newsroom.event_fingerprint import detect_event_type, detect_second_occurrence, tokens

# event types that can never inherit an unrelated context: an incident/market
# report is self-contained (§19 «unrelated category» reset)
HARD_BOUNDARY_TYPES = ("MILITARY_STRIKE", "LIVE_INCIDENT", "INTERNET_OUTAGE",
                       "MARKET_MOVE")

# deterministic NP-before-said-verb extraction — same rule as GATE-03 actor fill
_SPOKEN_RE = re.compile(r"^([؀-ۿ\w ]{3,40}?)\s+(?:گفت|اعلام کرد|اظهار کرد)")


def is_prefix_item(text: str) -> bool:
    """True only for genuine CONTEXT_ONLY fragments: a first-line label (or
    connective opener) with no meaningful body — same boundary as GATE-03
    (claim_completeness.evaluate). A label WITH a substantial body is a
    complete item carrying its own explicit speaker."""
    t = (text or "").strip()
    first = t.split("\n", 1)[0]
    if not is_prefix_fragment(first):
        return False
    if "\n" not in t:
        return True
    return len(t.split("\n", 1)[1].strip()) < _MIN_MEANINGFUL_TOKENS * 2


def is_colon_label(text: str) -> bool:
    """True when the FIRST LINE is a speaker/context label ending with ':'.
    Only colon labels carry context value; bare connectives («در همین حال»)
    are CONTEXT_ONLY for publication but never establish/reset context."""
    first = (text or "").strip().split("\n", 1)[0].strip()
    return bool(first) and (first.endswith(":") or first.endswith("："))


def label_of(text: str) -> str:
    """Colon-label text without the trailing colon («ترامپ به مجله تایم:» →
    «ترامپ به مجله تایم»). Empty string when absent."""
    first = (text or "").strip().split("\n", 1)[0].strip()
    if first.endswith(":") or first.endswith("："):
        return first.rstrip(":：").strip()
    return ""


def extract_explicit_speaker(text: str) -> str | None:
    """Explicit speaker of a COMPLETE item: first-line colon label, a leading
    «ترامپ: …» label with content, else a leading NP before a said-verb.
    None = no explicit speaker (a candidate for contextless-quote
    inheritance, REG-039)."""
    t = (text or "").strip()
    if not t:
        return None
    first = t.split("\n", 1)[0].strip()
    if first.endswith(":") or first.endswith("："):
        return first.rstrip(":：").strip() or None
    from app.newsroom.claim_model import _LEADING_LABEL_RE, _is_identity_label

    m = _LEADING_LABEL_RE.match(t)
    if m and _is_identity_label(m.group(1)):
        return m.group(1).strip()
    m = _SPOKEN_RE.match(normalize(t))
    return m.group(1).strip() if m else None


def _same_speaker(a: str | None, b: str | None) -> bool:
    """Containment match either way — «ترامپ» inside «ترامپ به مجله تایم» is
    the SAME speaker; «نتانیاهو» is not."""
    na, nb = normalize(a or "").strip(), normalize(b or "").strip()
    if not na or not nb:
        return False
    return na in nb or nb in na


@dataclass
class ContextDecision:
    """Outcome of feeding one RawItem through the per-source context rules."""
    decision: str                       # PREFIX_STORED / INHERIT / RESET / NO_CONTEXT / CONNECTIVE_FRAGMENT
    inherited: dict | None = None       # live context applied to this item
    reasons: list[str] = field(default_factory=list)
    stored_context: dict | None = None  # only for PREFIX_STORED


def _row_to_ctx(row: dict) -> dict:
    return {
        "source_id": row["source_id"],
        "speaker": row["speaker"],
        "context_ref": row["context_ref"],
        "topic_tokens": json.loads(row["topic_tokens"] or "[]"),
        "event_type": row["event_type"],
        "raw_item_id": row["raw_item_id"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
    }


def load_live_context(db, source_id: int, *, now: str) -> dict | None:
    """Live context for source, or None when absent OR expired (TTL §4).
    Read-only; expired rows are simply never returned."""
    row = db.query_one(
        "SELECT * FROM source_context WHERE source_id=?", (source_id,))
    if not row:
        return None
    if str(row["expires_at"]) <= now:  # TTL expiry / large time gap
        return None
    return _row_to_ctx(row)


def upsert_context_from_prefix(db, *, source_id: int, raw_item_id: int | None,
                               text: str, now: str, ttl_seconds: int,
                               reason_code: str = "SPEAKER_OR_CONTEXT_PREFIX") -> dict:
    """Colon-label prefix → replaces the source's live context (newest wins).
    Bounded: at most ONE row per source, so replays/retries cannot duplicate
    context records (§12). Returns the stored context."""
    label = label_of(text)
    etype = detect_event_type(label or text or "")
    toks = sorted(tokens(label or text or ""))
    expires = _iso_plus(now, ttl_seconds)
    db.execute(
        "INSERT INTO source_context(source_id, speaker, context_ref, topic_tokens,"
        " event_type, raw_item_id, reason_code, created_at, expires_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(source_id) DO UPDATE SET speaker=excluded.speaker,"
        " context_ref=excluded.context_ref, topic_tokens=excluded.topic_tokens,"
        " event_type=excluded.event_type, raw_item_id=excluded.raw_item_id,"
        " reason_code=excluded.reason_code, created_at=excluded.created_at,"
        " expires_at=excluded.expires_at",
        (source_id, label, label, json.dumps(toks, ensure_ascii=False),
         etype, raw_item_id, reason_code, now, expires))
    return {
        "source_id": source_id, "speaker": label, "context_ref": label,
        "topic_tokens": toks, "event_type": etype, "raw_item_id": raw_item_id,
        "created_at": now, "expires_at": expires,
    }


def _iso_plus(ts: str, seconds: int) -> str:
    import datetime

    return (datetime.datetime.fromisoformat(ts)
            + datetime.timedelta(seconds=seconds)).isoformat()


def resolve_context(db, *, source_id: int, raw_item_id: int | None, text: str,
                    now: str, ttl_seconds: int) -> ContextDecision:
    """Main entry — deterministic per-source context rules for one RawItem.

    - colon-label prefix → stored as the source's new context (never inherited
      by itself; alone it produces 0 claims/events/stories/publications)
    - bare connective fragment → no context effect
    - complete item → inherit live compatible context, or RESET (context
      cleared) on an explicit boundary; expired context = NO_CONTEXT
    """
    t = (text or "").strip()
    if is_prefix_item(t):
        if is_colon_label(t):
            ctx = upsert_context_from_prefix(
                db, source_id=source_id, raw_item_id=raw_item_id, text=t,
                now=now, ttl_seconds=ttl_seconds)
            return ContextDecision("PREFIX_STORED", reasons=["COLON_LABEL"],
                                   stored_context=ctx)
        return ContextDecision("CONNECTIVE_FRAGMENT",
                               reasons=["NO_CONTEXT_VALUE"])
    if not t:
        return ContextDecision("NO_CONTEXT", reasons=["EMPTY_TEXT"])

    ctx = load_live_context(db, source_id, now=now)
    if ctx is None:
        return ContextDecision("NO_CONTEXT", reasons=["NO_LIVE_CONTEXT"])

    # R2 — explicit new speaker (§19)
    speaker = extract_explicit_speaker(t)
    if speaker and ctx["speaker"] and not _same_speaker(speaker, ctx["speaker"]):
        _clear(db, source_id)
        return ContextDecision("RESET", reasons=["EXPLICIT_NEW_SPEAKER",
                                                 "CONTEXT_CLEARED"])
    # R3 — explicit event boundary marker («حمله دوم», «دور جدید», …)
    if detect_second_occurrence(t):
        _clear(db, source_id)
        return ContextDecision("RESET", reasons=["EVENT_BOUNDARY_MARKER",
                                                 "CONTEXT_CLEARED"])
    etype = detect_event_type(t)
    # R4 — hard category switch: incident/market reports never inherit an
    # unrelated context (§19 «unrelated category»)
    if etype in HARD_BOUNDARY_TYPES and etype != ctx["event_type"]:
        _clear(db, source_id)
        return ContextDecision("RESET", reasons=["HARD_CATEGORY_SWITCH",
                                                 "CONTEXT_CLEARED"])
    # R5 — clear topic change: zero topic-token overlap AND different event
    # type, unless this is an interview/quote continuation (REG-029/REG-039)
    overlap = tokens(t) & set(ctx["topic_tokens"])
    if not overlap and etype != ctx["event_type"]:
        quote_continuation = (speaker is None) and (
            detect_class(t) == ClaimClass.QUOTE or ctx["event_type"] == "INTERVIEW")
        if not quote_continuation:
            _clear(db, source_id)
            return ContextDecision("RESET", reasons=["CLEAR_TOPIC_CHANGE",
                                                     "CONTEXT_CLEARED"])
    return ContextDecision("INHERIT", inherited=ctx,
                           reasons=["SAME_SOURCE", "WITHIN_TTL", "COMPATIBLE"])


def _clear(db, source_id: int) -> None:
    db.execute("DELETE FROM source_context WHERE source_id=?", (source_id,))
