"""GATE-03 claim-completeness (P3-A) — class-aware, explicit result states.

RawItem is NEVER dropped: classification only. CONTEXT_ONLY/INCOMPLETE items
stay persisted evidence and are never publishable alone (INV-002/011, REG-031).
"""
from __future__ import annotations

import re

from app.newsroom.claim_model import (  # noqa: F401
    _MIN_MEANINGFUL_TOKENS,
    ClaimClass, CompletenessResult, _CONNECTIVE_STARTS, _PREFIX_RE,
    certainty_of, extract_structured, has_negation, is_prefix_fragment,
    numbers_of,
)

CONTEXT_ONLY = "CONTEXT_ONLY"
COMPLETE = "COMPLETE"
INCOMPLETE = "INCOMPLETE"

_REQUIRED_SLOTS = {
    ClaimClass.QUOTE: ("actor", "predicate"),
    ClaimClass.ATTACK: ("predicate", "object_"),       # actor may be genuinely unknown
    ClaimClass.CASUALTY: ("predicate", "quantity"),    # context+count; attribution via certainty
    ClaimClass.MARKET: ("object_", "predicate", "time_ref"),
    ClaimClass.INTERNET: ("location", "predicate"),
    ClaimClass.GENERAL: ("predicate",),
}


def evaluate(text: str, source_language: str = "fa",
             speaker_hint: str | None = None) -> CompletenessResult:
    """Classify raw item text for claim eligibility. Never mutates evidence."""
    t = (text or "").strip()
    if not t:
        return CompletenessResult(INCOMPLETE, "EMPTY_TEXT", publishable=False)
    if is_prefix_fragment(t.split("\n", 1)[0]) and (
            "\n" not in t or len(t.split("\n", 1)[1].strip()) < _MIN_MEANINGFUL_TOKENS * 2):
        return CompletenessResult(CONTEXT_ONLY, "SPEAKER_OR_CONTEXT_PREFIX",
                                  publishable=False)
    for c in _CONNECTIVE_STARTS:
        if t.startswith(c) and len(t) <= 60:
            return CompletenessResult(CONTEXT_ONLY, "CONNECTIVE_FRAGMENT",
                                      publishable=False)
    cls = detect_class(t)
    claim = extract_structured(t, source_item_id=0, speaker_hint=speaker_hint)
    # GATE-11-adjacent: 'گفت/اعلام کرد' inside text = attributed statement → actor
    # is the leading NP before said-verb, deterministic: first 3 tokens before گفت.
    if cls == ClaimClass.QUOTE and not claim.actor:
        m = re.match(r"^([؀-ۿ\w ]{3,40}?)\s+(?:گفت|اعلام کرد|اظهار کرد)", t)
        if m:
            claim.actor = m.group(1).strip()
    missing = [slot for slot in _REQUIRED_SLOTS.get(cls, ("predicate",))
               if not getattr(claim, slot, None)]
    # deterministic containment fill: keyword evidence in text satisfies
    # target/area slots without fabricating structured values
    if cls == ClaimClass.INTERNET and "location" in missing:
        for kw in ("استان", "شهر", "کشور", "منطقه", "سراسر"):
            if kw in t:
                missing.remove("location")
                break
    if cls == ClaimClass.ATTACK and "object_" in missing:
        for kw in ("منطقه", "شهر", "مرز", "پایگاه", "مقر", "کشور", "بغداد", "تهران",
                          "اسرائیل", "عراق", "سوریه", "لبنان", "یمن", "امریکا", "آمریکا"):
            if kw in t:
                missing.remove("object_")
                break
    # slot-fill fallbacks from deterministic extraction (never fabricated):
    if cls == ClaimClass.MARKET and "object_" in missing:
        for kw in ("دلار", "طلا", "سکه", "بورس", "شاخص", "نفت", "ارز", "تومان", "یورو"):
            if kw in t:
                missing.remove("object_")
                break
    if cls == ClaimClass.MARKET and "time_ref" in missing:
        if claim.time_ref or "امروز" in t or "امشب" in t:
            missing.remove("time_ref")
    if missing:
        return CompletenessResult(
            INCOMPLETE, "MISSING_SLOTS", missing_slots=missing, publishable=False)
    # meaningful standalone proposition: enough tokens, not speaker-only
    if len([w for w in t.split() if len(w) > 1]) < _MIN_MEANINGFUL_TOKENS:
        return CompletenessResult(INCOMPLETE, "TOO_FEW_TOKENS", publishable=False)
    return CompletenessResult(COMPLETE, publishable=True)


def detect_class(text: str):
    from app.newsroom.claim_model import detect_class as _d

    return _d(text)


def has_negation(text: str) -> bool:
    from app.newsroom.claim_model import has_negation as _h

    return _h(text)


def numbers_of(text: str):
    from app.newsroom.claim_model import numbers_of as _n

    return _n(text)


def certainty_of(text: str) -> str:
    from app.newsroom.claim_model import certainty_of as _c

    return _c(text)
