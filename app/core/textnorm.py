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


_PERSIAN_ONLY = set("پچژگکی")
_ARABIC_ONLY = set("يكةىؤإ")
_FA_WORDS = set(("را از در با برای این آن یک است شد شدند کرد کردند گفت گفتند می نمی "
                 "خواهد دارد دارند امروز افزایش کاهش یافت رسید داد اعلام").split())
_AR_WORDS = set(("في من على عن أن إن إلى الى التي الذي هذا هذه مع قد لا ما لم لن "
                 "كان كانت يكون قال قالت أعلن أعلنت اليوم عاجل بعد بين عبر نحو أكثر حتى حيث حول").split())
_AR_WORDS = {w.replace("ي", "ی").replace("ك", "ک") for w in _AR_WORDS}


def language_content(text: str) -> str:
    """Exclude metadata from language detection; a footer is not evidence."""
    lines = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith(("—", "منبع:", "منابع:", "🆔")):
            continue
        line = re.sub(r"https?://\S+|t\.me/\S+|@[A-Za-z0-9_]{3,}", " ", line)
        lines.append(line)
    return "\n".join(lines)


def _language_scores(text: str) -> tuple[int, int]:
    words = set(re.findall(r"[^\W\d_]+", normalize_text_for_hash(text)))
    return len(words & _FA_WORDS), len(words & _AR_WORDS)


def is_native_persian(text: str) -> bool:
    """Positive Persian syntax, independent of source labels or Latin names.

    Ambiguous shared-script text stays on the configured-source path. Each
    substantive sentence must qualify, so a Persian line cannot mask a foreign
    paragraph. This is routing evidence, not a substitute for publication QA.
    """
    content = language_content(text)
    parts = [p for p in re.split(r"[\n.!?؟]+", content) if any(c.isalpha() for c in p)]
    if not parts:
        return False
    for part in parts:
        letters = [c for c in part if c.isalpha()]
        fa, ar = _language_scores(part)
        if (fa < 2 or fa <= ar or
                sum("\u0600" <= c <= "\u06ff" for c in letters) / len(letters) < 0.5):
            return False
    return True


def detect_language(text: str) -> str:
    t = language_content(text)
    fa, ar = _language_scores(t)
    # Arabic grammar wins over Persian letters in names (e.g. عراقچی).
    if ar >= 2 and ar > fa:
        return "ar"
    if is_native_persian(t):
        return "fa"
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
