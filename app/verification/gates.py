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


_TOPIC_WEIGHTS = {
    "WAR_MILITARY": (100, [
        "جنگ", "حمله موشکی", "پهپاد", "نظامی", "بمبار", "تحریم نظامی", "missile", "strike", "military", "war",
        "حرب", "عسكري", "عسکری", "الجیش", "الجيش", "قوات", "هجوم", "غارة", "غارات", "قصف",
        "صاروخ", "صواريخ", "صواریخ", "مسيرة", "مسيرات", "طائرة مسيرة", "طائرات", "دفاع جوي",
        "دفاع هوایی", "انفجار", "اشتباكات", "اشتباکات", "جبهة", "قاعدة عسكرية", "تحرك عسكري",
        "انتشار", "استهداف", "اغتیال", "کشته", "قتل"]),
    "INTERNET": (95, ["اینترنت", "فیلترینگ", "قطعی اینترنت", "اتصال", "پهنای باند", "internet",
                      "shutdown", "filternet", "انترنت", "قطع الانترنت", "حجب", "اتصالات", "شبكة", "شبكات", "تعطيل"]),
    "CURRENCY": (92, ["دلار", "ارز", "تومان", "طلا", "سکه", "بورس", "دولار", "صرف", "عملة",
                      "عملات", "ذهب", "سعر الصرف", "dollar", "currency", "gold", "fx"]),
    "DIPLOMACY": (88, ["دیپلماس", "مذاکره", "وزیر خارجه", "سفیر", "diplomat", "talks", "مفاوضات", "خارجية"]),
    "IRAN_IRAQ": (88, ["ایران", "تهران", "مجلس", "رئیس‌جمهور", "عراق", "بغداد", "ایربیل", "اربیل",
                       "بصره", "iraq", "baghdad", "کرمانشاه"]),
    "ECONOMY": (75, ["اقتصاد", "نفتی", "بازار", "تورم", "economy", "oil", "نفط"]),
    "TECH": (60, ["فناوری", "هوش مصنوعی", "تراشه", "ai", "chip", "tech"]),
    "SPORT": (15, ["فوتبال", "football", "soccer", "كرة القدم", "کرة القدم", "باشگاه", "لیگ",
                   "مباراة", "مسابقه", "olympic", "المپیک", "المپیاد", "دویدن", "goal", "وردی"]),
    "ENTERTAINMENT": (15, ["سلبریتی", "بازیگر", "سینما", "موسیقی", "کنسرت", "تفریحی", "celebrity",
                           "فیلم", "سریال", "شو", "استیج"]),
}
def priority_tier(weight: int) -> str:
    """Iran-first story priority (directive 2026-10-04): P0 Iran-critical
    (war/security/nuclear/sanctions/internet/currency/diplomacy), P1 regional,
    P2 relevant world, P3 other. ORDER only — never verification trust."""
    if weight >= 88:
        return "P0"
    if weight >= 75:
        return "P1"
    if weight >= 60:
        return "P2"
    return "P3"


_LOW_TOPICS = {"SPORT", "ENTERTAINMENT"}


def classify_priority(text: str) -> tuple[str, int]:
    """Multilingual (fa/ar/en) topic weight → queue priority.
    Affects ORDER only — never drops an item and never touches verification trust."""
    t = (text or "").lower().replace("ي", "ی").replace("ك", "ک")
    best_topic, best_w = "GENERAL_IMPORTANT", 50
    for topic, (w, kws) in _TOPIC_WEIGHTS.items():
        for k in kws:
            k2 = k.lower().replace("ي", "ی").replace("ك", "ک")
            if k2 in t:
                if topic in _LOW_TOPICS:
                    if best_topic == "GENERAL_IMPORTANT":
                        best_topic, best_w = topic, w
                    continue
                if w > best_w:
                    best_topic, best_w = topic, w
                break
    return best_topic, best_w


_SPEAKER_LINE_RE = None  # set below
import re as _re

def split_speaker_label(text: str):
    """Telegram convention: a first line like a name/flag + ':' is a SPEAKER
    LABEL, never a headline. Returns (speaker, body)."""
    global _SPEAKER_LINE_RE
    if _SPEAKER_LINE_RE is None:
        _SPEAKER_LINE_RE = _re.compile(
            r"^[^\w\s]*[\U0001F1E6-\U0001F1FF]{0,2}\s*[\u0600-\u06FF\w .'\-]{2,40}\s*[:\uff1a]\s*$")
    lines = [ln.strip() for ln in (text or "").split(chr(10)) if ln.strip()]
    if not lines:
        return None, ""
    if _SPEAKER_LINE_RE.match(lines[0]):
        speaker = lines[0].strip().rstrip(":").rstrip("：").strip()
        return speaker, chr(10).join(lines[1:])
    return None, chr(10).join(lines)



_EMPTY_HEADLINE_WORDS = {"عاجل", "فوری", "breaking", "خبر", "خبر فوری", "مهم"}

def is_valid_headline(h: str) -> bool:
    """MIN_HEADLINE_INFORMATION: a real proposition, not a speaker label/flag/name."""
    if not h:
        return False
    t = h.strip().rstrip(":：").strip()
    if not t or t.endswith(":") or t.endswith("："):
        return False
    if any(ch.isascii() for ch in t) and len(t) < 15:
        pass
    if t in _EMPTY_HEADLINE_WORDS:
        return False
    words = [w for w in _re.split(r"\s+", t) if w.strip("🇦🇿🇺🇸🇮🇷🇮🇶:：.،") and len(w) > 1]
    if len(words) < 3:
        return False
    if len(t) < 15:
        return False
    emoji_only = all(not any(c.isalpha() for c in w) for w in words)
    return not emoji_only


def extract_headline(title: str, text: str) -> str:
    """Best meaningful headline: skip speaker labels and low-info first lines."""
    speaker, body = split_speaker_label((title or "") + chr(10) + "" + (text or ""))
    lines = [ln.strip() for ln in body.split(chr(10)) if ln.strip()] if body else []
    for ln in lines[:5]:
        if is_valid_headline(ln):
            return ln[:140]
    # fall back to longest line
    if lines:
        cand = max(lines, key=len)
        if is_valid_headline(cand):
            return cand[:140]
    return ""
