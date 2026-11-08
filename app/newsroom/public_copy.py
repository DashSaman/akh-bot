"""Deterministic rejection of operational prose masquerading as public news.

These checks supplement evidence/language gates; they do not score factual truth.
Patterns target notices and assistant refusals, not news reporting on such errors.
"""
from __future__ import annotations

import re

_ERROR_NOTICES = tuple(re.compile(p, re.I) for p in (
    r"^خطا(?:ی|\s+در)?\s+ترجمه(?:\s*[:：.!]|$)",
    r"^این\s+(?:خبر|متن|مطلب).{0,60}(?:اشکال|خطا|مشکل)\s+(?:در\s+)?ترجمه.{0,80}(?:بازبینی|بررسی|ناموفق)",
    r"^ترجمه\s+(?:این\s+)?(?:متن|خبر|مطلب).{0,100}(?:امکان\s*پذیر\s*نیست|ناموفق|خطا)",
    r"^(?:مت[أا]سفم[،,\s]*)?(?:من\s+)?نمی\s*توانم.{0,80}(?:ترجمه|پردازش|خلاصه\s*سازی)",
    r"^(?:مت[أا]سفم[،,\s]*)?امکان\s+(?:ترجمه|پردازش).{0,100}(?:نیست|ندارد)",
    r"^(?:translation\s+(?:error|failed)|error\s+(?:in\s+)?translation)\b",
    r"^(?:sorry[,!\s]*)?i\s+(?:cannot|can't|am\s+unable\s+to).{0,80}(?:translate|summari[sz]e|process)\b",
))
_BROADCAST = re.compile(
    r"^(?:تازه\s*ترین|آخرین|جدیدترین)\s+(?:خبرها|اخبار|خبرهای).{0,180}(?:رادیو|پادکست|برنامه)")
_MIXED_WORD = re.compile(r"[A-Za-z][\u0621-\u064a\u0671-\u06d3]|[\u0621-\u064a\u0671-\u06d3][A-Za-z]")
_DANGLING_END = re.compile(
    r"(?:^|\s)(?:در|از|به|برای|بین|و|که|با|درباره|اگر|را|اما|یا|[\u0621-\u064a\u0671-\u06d3])\s*[.!؟،؛:]*$")


def unpublishable_copy_reason(headline: str, body: str = "") -> str | None:
    lines = []
    for line in ((headline or "") + "\n" + (body or "")).splitlines():
        line = line.strip()
        if not line or line.startswith(("منبع:", "منابع:", "—", "🆔", "@")):
            continue
        line = line.replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
        line = re.sub(r"[\u064b-\u065f\u0670*]", "", line)
        line = re.sub(r"^[^\w\u0600-\u06ff]+", "", line).strip()
        if line:
            lines.append(line)
    if any(p.search(line) for line in lines for p in _ERROR_NOTICES):
        return "HOLD_TRANSLATION_QUALITY"
    if any(_MIXED_WORD.search(line) for line in lines):
        return "HOLD_TRANSLATION_QUALITY"
    if any(_DANGLING_END.search(line) or line.endswith(("…", "...")) for line in lines):
        return "CONTEXT_INCOMPLETE"
    # A program announcement without actual reporting is not a standalone news item.
    non_generic = [line for line in lines if not line.startswith((
        "این ادعا تا این لحظه به تأیید مستقل نرسیده", "پایش ادامه دارد"))]
    if non_generic and all(_BROADCAST.search(line) for line in non_generic):
        return "HOLD_NON_NEWS_CONTENT"
    return None
