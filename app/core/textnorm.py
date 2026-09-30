"""Text normalization + hashing used by dedup stages 1-4.

Canonical URL → exact content hash → normalized title → SimHash.
Never send these computations to an LLM.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "ref_src", "igshid", "si", "mibextid",
}

_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

# Persian/Arabic unification: ي→ی ك→ک arabic-indic digits kept as-is (values matter)
_ARABIC_YEH = "\u064a"
_PERSIAN_YEH = "\u06cc"
_ARABIC_KAF = "\u0643"
_PERSIAN_KEHEH = "\u06a9"
_DIACRITICS = re.compile(r"[\u064b-\u065f\u0670]")


def canonical_url(url: str) -> str:
    """Stage 1 key: strip tracking params, fragment, default ports, sort query."""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    scheme = parts.scheme.lower() or "http"
    host = (parts.hostname or "").lower()
    if not host:
        return url.strip()
    try:
        port = parts.port
    except ValueError:
        port = None
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    path = quote(parts.path or "/", safe="/%:@")
    path = re.sub(r"/+$", "", path) or "/"
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    q.sort()
    query = "&".join(f"{k}={v}" for k, v in q)
    return urlunsplit((scheme, host, path, query, ""))


def normalize_text_for_hash(text: str) -> str:
    """Aggressive normalization for exact/near duplicate hashing (display text is never overwritten)."""
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace(_ARABIC_YEH, _PERSIAN_YEH).replace(_ARABIC_KAF, _PERSIAN_KEHEH)
    t = _DIACRITICS.sub("", t)
    t = _ZERO_WIDTH.sub("", t)
    t = _TAGS.sub(" ", t)
    t = _WS.sub(" ", t).strip().lower()
    return t


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text_for_hash(text).encode()).hexdigest()


def normalize_title(title: str) -> str:
    """Stage 3 key: normalized title (shared wording across outlets collapses here)."""
    t = normalize_text_for_hash(title)
    t = re.sub(r"[«»\"'()\[\]{}\-.،؛:!؟?…]", " ", t)
    return _WS.sub(" ", t).strip()


def title_hash(title: str) -> str:
    return hashlib.sha256(normalize_title(title).encode()).hexdigest()


_PERSIAN_ONLY = set("پچژگآ")
_ARABIC_ONLY = set("يكةىؤإ")


def detect_language(text: str) -> str:
    t = text or ""
    if any(ch in _PERSIAN_ONLY for ch in t):
        return "fa"
    if any(ch in _ARABIC_ONLY for ch in t) or "\u0627" in t:
        return "ar"
    if re.search(r"[а-яА-Я]", t):
        return "ru"
    if re.search(r"[a-zA-Z]", t):
        return "en"
    return "und"


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()
