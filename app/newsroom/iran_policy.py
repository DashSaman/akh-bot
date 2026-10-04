"""Iran-first editorial policy: capacity allocation + crisis mode.

90% is an editorial ALLOCATION TARGET when enough valid Iran-related stories
exist — never fabricated, never a rigid per-hour arithmetic. Spare capacity
spills to regional/global news automatically. IRAN_CRISIS_MODE concentrates
speed and capacity further but NEVER weakens verification (priority is order,
not trust — same invariant as source speed priority).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

IRAN_SHARE_TARGET = 0.70   # rolling-6h floor before P2/P3 deferral kicks in
IRAN_SHARE_CRISIS = 0.90   # allocation target while crisis mode is active
CRISIS_KEY = "IRAN_CRISIS_MODE"
CRISIS_TRIGGER_EVENTS = 2  # distinct-source P0 war events in the window
CRISIS_WINDOW_MIN = 30

_IRAN_MARKERS = (
    "ایران", "تهران", "اصفهان", "مشهد", "تبریز", "شیراز", "اهواز", "کرمان",
    "قم", "یران", "persian gulf", "hormuz", "tehran", "iran", "irani",
    "irgc", "sepah", "بسیج", "آیت", "خامنه", "peacock",
    "تومان", "ریال", "فیلترینگ", "اینترنت", "سپاه", "ARD", "سنجاقک",
    "بوشهر", "نطنز", "فردو", "اراک", "IAEA", "آژانس", "تحریم",
)


def is_iran_related(text: str) -> bool:
    t = (text or "").lower()
    return any(m.lower() in t for m in _IRAN_MARKERS)


def iran_waiting_count(db) -> int:
    """Never-sent stories that are Iran-related (supply for allocation)."""
    rows = db.query(
        "SELECT st.id, st.headline FROM stories st"
        " WHERE st.status='DRAFT' AND NOT EXISTS ("
        "  SELECT 1 FROM publications p WHERE p.story_id = st.id"
        "  AND p.status='SENT')")
    return sum(1 for r in rows if is_iran_related(r["headline"] or ""))


def iran_share_6h(db) -> float:
    """Share of NEW posts in the rolling 6h window that are Iran-related."""
    since = (datetime.now(timezone.utc) - timedelta(hours=6)) \
        .isoformat(timespec="seconds")
    rows = db.query(
        "SELECT st.headline FROM publications p JOIN stories st ON st.id = p.story_id"
        " WHERE p.status='SENT' AND p.created_at>=? AND NOT EXISTS ("
        "  SELECT 1 FROM publications q WHERE q.story_id = p.story_id"
        "  AND q.status='SENT' AND q.id < p.id)", (since,))
    if not rows:
        return 0.0
    return sum(1 for r in rows if is_iran_related(r["headline"] or "")) / len(rows)


def defer_for_iran_capacity(db, headline: str, weight: int) -> bool:
    """SOFT allocation: a P2/P3 story waits one pass when the rolling Iran
    share is under target AND Iran supply genuinely exists. Never defers
    when Iran supply is empty (capacity spills automatically) and never
    touches P0/P1."""
    if weight >= 75:  # P0/P1 always pass
        return False
    if iran_share_6h(db) >= IRAN_SHARE_TARGET:
        return False
    return iran_waiting_count(db) > 0


# ---------------------------------------------------------------- crisis mode
def update_crisis_mode(db, *, calm_minutes: int = 60) -> dict[str, Any]:
    """Auto-trigger/extend/expire IRAN_CRISIS_MODE on strong evidence.

    Trigger: >=2 distinct-source P0 war/security events about Iran inside the
    window. While active, fresh triggers extend it; it expires after the calm
    period with NO manual restart. Verification is never weakened — crisis
    only concentrates speed/capacity.
    """
    from app.db.repo import SettingsRepo
    now = datetime.now(timezone.utc)
    state: dict[str, Any] = {}
    raw = SettingsRepo(db).get(CRISIS_KEY) or ""
    if raw:
        try:
            state = json.loads(raw)
        except (ValueError, TypeError):
            state = {}
    since = (now - timedelta(minutes=CRISIS_WINDOW_MIN)) \
        .isoformat(timespec="seconds")
    triggers = db.query(
        "SELECT DISTINCT st.event_id FROM stories st"
        " JOIN events e ON e.id = st.event_id"
        " WHERE st.created_at >= ? AND (e.importance >= 90 OR e.velocity >= 90)"
        "   AND (st.headline LIKE '%ایران%' OR st.headline LIKE '%تهران%'"
        "        OR st.headline LIKE '%Iran%')", (since,))
    n = len({t["event_id"] for t in triggers})
    active = bool(state.get("active")) and str(state.get("until", "")) > \
        now.isoformat(timespec="seconds")
    if n >= CRISIS_TRIGGER_EVENTS:
        until = (now + timedelta(minutes=calm_minutes)) \
            .isoformat(timespec="seconds")
        state = {"active": True, "since": state.get("since") if active
                 else now.isoformat(timespec="seconds"), "until": until,
                 "triggers": n}
    elif active:
        state["active"] = False  # calm period elapsed -> auto-exit
        state["exited_at"] = now.isoformat(timespec="seconds")
    else:
        state.setdefault("active", False)
    SettingsRepo(db).set(CRISIS_KEY, json.dumps(state, ensure_ascii=False))
    return state


def crisis_active(db) -> bool:
    from app.db.repo import SettingsRepo
    raw = SettingsRepo(db).get(CRISIS_KEY) or ""
    if not raw:
        return False
    try:
        state = json.loads(raw)
    except (ValueError, TypeError):
        return False
    if not state.get("active"):
        return False
    return str(state.get("until", "")) > \
        datetime.now(timezone.utc).isoformat(timespec="seconds")
