"""Iran-first editorial policy: capacity allocation + crisis mode.

~90% Iran-related allocation WHEN enough valid Iran-related supply exists —
never manufactured filler; unused capacity spills to regional/global news
automatically. Classification requires a MATERIAL relation to Iran (people,
government/security/military, IRGC, Israel/US ties, nuclear/IAEA, sanctions,
negotiations, threats either direction, Hormuz/Persian Gulf, economy/
currency, internet restrictions, Iran-adjacent escalation) — not a random
keyword coincidence.

IRAN_CRISIS_MODE state machine (FINAL-HARDENING §3):
  INACTIVE --(>= threshold fresh triggers)--> ACTIVE (until = now + calm)
  ACTIVE   --(new trigger)-------------------> extend until = now + calm
  ACTIVE   --(no trigger, now < until)-------> REMAIN ACTIVE (never early-exit)
  ACTIVE   --(no trigger, now >= until)------> INACTIVE
Verification rules NEVER change in crisis (priority is order, not trust).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

IRAN_SHARE_TARGET = 0.90   # owner policy: ~90% when sufficient valid supply
CRISIS_KEY = "IRAN_CRISIS_MODE"
CRISIS_TRIGGER_EVENTS = 2  # distinct P0 Iran events inside the window
CRISIS_WINDOW_MIN = 30

# Material-relation markers: multiword phrases and Iran-specific terms.
# Generic words alone (اینترنت، gold, war…) must NOT classify world news.
_IRAN_PHRASES = (
    "ایران", "تهران", "اصفهان", "مشهد", "تبریز", "شیراز", "اهواز", "کرمان",
    "قم", "کرج", "رشت", "زاهدان", "بندرعباس", "خلیج فارس", "تنگه هرمز",
    "هرمز", "آبادان", "بوشهر", "نطنز", "فردو", "اراک", "خوزستان",
    "سپاه پاسداران", "سپاه", "قدس", "بسیج", "irgc",
    "آیت الله", "رهبر انقلاب", "مجلس شورای اسلامی", "قوه قضائیه",
    "رئیس جمهور ایران", "وزیر خارجه ایران", "دیپلمات ایران",
    "تحریم", "sanction", "sanctions",
    "تومان", "ریال", "دلار تهران", "بورس تهران",
    "فیلترینگ", "شبکه ملی اطلاعات",
    "irna", "irib", "persian gulf", "hormuz", "strait of hormuz",
    "irani", "iranian", "iran", "tehran", "qom", "mashhad",
    "iaea", "آژانس بین المللی انرژی اتمی", "آژانس",
    "انرژی اتمی ایران", "برنامه هسته‌ای", "هسته‌ای", "غنی‌سازی",
)
# words that look Iran-ish but alone mean generic world news → require combo
_GENERIC_BLOCKERS = ("فوتبال", "سینما", "سلبریتی", "باشگاه", "لیگ قهرمانان",
                     "جام جهانی", "المپیک", "olympic", "celebrity", "league",
                     "cup final", "box office")


def is_iran_related(text: str) -> bool:
    """Material relation to Iran — with a sports/entertainment negative
    control so routine filler never masquerades as Iran priority."""
    t = (text or "").lower()
    if not t:
        return False
    if any(b in t for b in _GENERIC_BLOCKERS):
        # "فوتبال ایران" IS Iran-related; pure generic filler is not
        has_core = any(m in t for m in ("ایران", "تهران", "iran", "irani"))
        if not has_core:
            return False
    return any(m in t for m in _IRAN_PHRASES)


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
    touches P0/P1 breaking."""
    if weight >= 75:  # P0/P1 breaking never waits behind P2/P3 backlog
        return False
    if iran_share_6h(db) >= IRAN_SHARE_TARGET:
        return False
    return iran_waiting_count(db) > 0


# ---------------------------------------------------------------- crisis mode
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def update_crisis_mode(db, *, calm_minutes: int = 60) -> dict[str, Any]:
    """Correct state machine — see module docstring. Never exits before
    `until` actually expires, regardless of fresh-trigger dips."""
    from app.db.repo import SettingsRepo
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")
    state: dict[str, Any] = {}
    raw = SettingsRepo(db).get(CRISIS_KEY) or ""
    if raw:
        try:
            state = json.loads(raw)
        except (ValueError, TypeError):
            state = {}
    until = str(state.get("until") or "")
    was_active = bool(state.get("active"))

    n = _fresh_trigger_count(db)
    if n >= CRISIS_TRIGGER_EVENTS:
        state = {"active": True,
                 "since": state.get("since") if was_active else now_iso,
                 "until": (now + timedelta(minutes=calm_minutes))
                 .isoformat(timespec="seconds"),
                 "triggers": n}
    elif was_active:
        if now_iso >= until:  # calm interval ACTUALLY elapsed
            state["active"] = False
            state["exited_at"] = now_iso
        # else: REMAIN ACTIVE — no early exit, no manual restart needed
    # else: was inactive and no trigger — stays inactive
    SettingsRepo(db).set(CRISIS_KEY, json.dumps(state, ensure_ascii=False))
    return state


def _fresh_trigger_count(db) -> int:
    since = (datetime.now(timezone.utc)
             - timedelta(minutes=CRISIS_WINDOW_MIN)) \
        .isoformat(timespec="seconds")
    rows = db.query(
        "SELECT DISTINCT st.event_id FROM stories st"
        " JOIN events e ON e.id = st.event_id"
        " WHERE st.created_at >= ? AND (e.importance >= 90 OR e.velocity >= 90)"
        "   AND (st.headline LIKE '%ایران%' OR st.headline LIKE '%تهران%'"
        "        OR st.headline LIKE '%Iran%')", (since,))
    return len({r["event_id"] for r in rows})


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
    return str(state.get("until", "")) > _now_iso()
