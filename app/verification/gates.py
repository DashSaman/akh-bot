"""Verification gates: high-risk claim detection and hard rules.

Rules + evidence indicators — never a bare numeric confidence threshold.
Separate VERIFICATION / IMPORTANCE / VELOCITY scores; virality is never proof.
"""
from __future__ import annotations

import re
from typing import Any

HIGH_RISK_PATTERNS = [
    r"(?:\d+\s*)?(?:کشته|قتل|جان ?باخت|تلفات|مجروح|زخمی)",          # casualties fa
    r"(?:قتلع|إصابات|خسائر بشرية|حصيلة)",                            # casualties ar
    r"(?:killed|casualt\w+|injur\w+|dead|wounded)",                  # casualties en
    r"(?:حمله نظامی|حمله موشکی|پیشمرگ|بمباران|تهاجم)",               # military fa
    r"(?:بازداشت|دستگیر)",                                           # arrests fa
    r"(?:اعلام مسئولیت|مسئولیت حمله)",                               # responsibility
    r"(?:اعلام جنگ|جنگ اعلام)",                                      # war
    r"(?:تصمیم رسمی|فرمان رسمی|تحریم جدید)",                         # major official action
]
_HIGH_RISK_RE = [re.compile(p, re.IGNORECASE) for p in HIGH_RISK_PATTERNS]

_NUM = re.compile(r"\d+")
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def is_high_risk(text: str) -> bool:
    return any(rx.search(text or "") for rx in _HIGH_RISK_RE)


def numbers_in(text: str) -> set[str]:
    """Digits as written in Persian/Arabic/Latin press — normalized to ASCII."""
    return set(_NUM.findall((text or "").translate(_FA_DIGITS)))


def decide_claim_state(claim_text: str, *, independent_sources: int,
                       has_contradiction: bool, risk: str) -> str:
    """Hard gates:
    - contradiction present → CONFLICTING (publish only attributed uncertainty)
    - high-risk + single origin → SINGLE_SOURCE (never a definitive headline)
    - >=2 independent origins → CORROBORATED (CONFIRMED reserved for official/primary evidence)
    """
    if has_contradiction:
        return "CONFLICTING"
    if independent_sources >= 2:
        return "CORROBORATED"
    if risk == "high":
        return "SINGLE_SOURCE"
    return "UNVERIFIED"


def event_can_auto_publish(claims: list[dict[str, Any]]) -> tuple[bool, str]:
    """Event-level gate: high-risk conflicting numbers block definitive publication."""
    conflicting = [c for c in claims if c["state"] == "CONFLICTING"]
    if conflicting:
        return False, "CONFLICTING_CLAIMS"
    high_risk_single = [c for c in claims if c["risk_level"] == "high" and c["state"] == "SINGLE_SOURCE"]
    if high_risk_single:
        return False, "HIGH_RISK_SINGLE_SOURCE"
    return True, "OK"
