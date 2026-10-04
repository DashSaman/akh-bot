"""Telegram channel publisher (Bot API). Idempotent via the publication ledger.

Public destinations are VALIDATED: a private chat is never a news target.
Public copy carries only OUR brand signature; evidence stays in the DB.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

log = logging.getLogger("akh.pub.telegram")

_URL_RE = re.compile(r"(?:https?://\S+|www\.\S+|t\.me/\S+)")
_SOURCE_LINE_RE = re.compile(r"^\s*(?:📖\s*)?(?:منبع|source)\s*[:：]", re.IGNORECASE)

STATUS_ICONS = {  # ICON-ONLY lifecycle indicators (channel description explains)
    "PROVISIONAL": "🔴",
    "CONFIRMED": "🟢",
    "CONFIRMED_OFFICIAL": "🟢",
    "CONFLICTING": "🟠",
    "RETRACTED": "❌",
    "UNCONFIRMED_UPDATE": "⚠️",
    "UNVERIFIED_EXPIRED": "⚠️",
}

_BOILERPLATE = (
    "بر پایه گزارش‌های رسیده",
    "این موارد از منابع تحت پایش راسته",
    "بررسی منابع نشان می‌دهد",
    "سامانه راستی‌آزمایی",
    "مطابق بررسی سیستم",
    "این اطلاعات تاکنون به‌طور مستقل تأیید نشده است",
    "تأیید شد",
)


def _norm_block(t: str) -> set:
    import re as _r
    t = (t or "").replace("ي", "ی").replace("ك", "ک").replace("**", "")
    t = _r.sub(r"[‌\s\W_]+", " ", t).strip().lower()
    return set(t.split())


def dedup_paragraphs(text: str, threshold: float = 0.6) -> str:
    """PUBLIC_TEXT_DUPLICATION_GATE: drop later paragraphs that restate earlier ones."""
    lines = text.split(chr(10))
    out, seen_sets = [], []
    for ln in lines:
        toks = _norm_block(ln)
        if len(toks) >= 6 and any(len(toks & p) / max(1, len(toks | p)) >= threshold for p in seen_sets):
            continue
        seen_sets.append(toks)
        out.append(ln)
    return chr(10).join(out)


def strip_boilerplate(text: str) -> str:
    lines = []
    for ln in (text or "").split(chr(10)):
        if any(b in ln for b in _BOILERPLATE) and len(ln) < 120:
            continue
        lines.append(ln)
    s2 = chr(10).join(lines)
    while chr(10) + chr(10) + chr(10) in s2:
        s2 = s2.replace(chr(10) * 3, chr(10) * 2)
    return s2.strip()


def brand_signature(brand: Any, enabled: bool = True) -> str:
    """Public footer = ONLY our own configured handle (no brand word, no sources)."""
    if not enabled:
        return ""
    handle = getattr(brand, "telegram_handle", "")
    name, tag = getattr(brand, "name_fa", ""), getattr(brand, "tagline_fa", "")
    lines = []
    if name and tag:
        lines.append(f"— {name} | {tag}")
    if handle:
        lines.append(f"🆔 @{handle}")
    return chr(10).join(lines)


def sanitize_public_copy(text: str, mode: str = "hidden", brand: Any = None) -> str:
    """PUBLIC_SOURCE_DISPLAY_MODE: hidden (default) / names_only / links."""
    handle = getattr(brand, "telegram_handle", "") or "\u0000"
    out = []
    for ln in text.split("\n"):
        if mode == "hidden" and _SOURCE_LINE_RE.match(ln):
            continue
        if mode != "links":
            ln = _URL_RE.sub("", ln)
            ln = re.sub(r"(?<![\w@])@(?!" + re.escape(handle) + r"\b)\w{3,}", "", ln)
        out.append(ln.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def build_public_text(status, body, brand, source_mode="hidden",
                      signature_enabled=True, source_names=""):
    icon = STATUS_ICONS.get(status, "")
    clean = strip_boilerplate(sanitize_public_copy(body, source_mode, brand))
    clean = dedup_paragraphs(clean)
    lines = clean.split(chr(10))
    if lines and "راسته؟ |" in lines[0]:
        lines = lines[1:]  # branding lives in the footer only
    while lines and not lines[0].strip():
        lines = lines[1:]
    if lines:
        first = lines[0].strip()
        bolded = first if first.startswith("**") else "**" + first + "**"
        head = " ".join(x for x in (icon, topic_emoji(first), bolded) if x)
        lines[0] = head
        clean = chr(10).join(lines)
    src = ("منبع: " + source_names) if source_names else ""
    sig = brand_signature(brand, signature_enabled)
    parts = [p for p in (clean, src, sig) if p]
    return (chr(10) + chr(10)).join(parts)


# URGENT-FIX §5 — generic status/warning-only public bodies (deadline-era
# regression): a public post whose stripped body is just this warning carries
# no actual claim context and must never go out alone
_GENERIC_STATUS_MARKERS = (
    "بررسی این موضوع در منابع در دسترس",
    "تا این لحظه به تأیید مستقل نرسیده است",
    "پایش ادامه دارد و در صورت تأیید",
)


def public_body_is_substantive(text: str) -> bool:
    """FINAL PUBLIC BODY GATE (fail-closed, SEND + EDIT): strip lifecycle
    icon, topic emoji, source line, brand footer, @handle and bold markers —
    a meaningful standalone Persian factual claim must remain. Rejects:
    empty body, source-only, footer-only, speaker-prefix-only, and
    generic-status-only bodies (owner screenshot regression)."""
    t = (text or "").strip()
    if not t:
        return False
    # strip markup/footer/source lines (mirror of build_public_text assembly)
    for line in list(_SOURCE_LINE_RE.finditer(t)):
        pass
    lines = []
    for ln in t.split(chr(10)):
        stripped = ln.strip()
        if _SOURCE_LINE_RE.match(stripped):          # منبع: ...
            continue
        if "راسته؟ |" in stripped or stripped.startswith("🆔 @"):
            continue                                  # footer lines
        if stripped.startswith(("🟢", "🔴", "🟠", "⚠️", "❌")):
            stripped = stripped.lstrip("🟢🔴🟠⚠️❌ ").strip()
        stripped = stripped.replace("*", "")
        if stripped:
            lines.append(stripped)
    body = chr(10).join(lines).strip()
    if not body:
        return False
    # generic status-only body (deadline regression): marker + no other claim
    non_generic = [ln for ln in lines
                   if not any(m in ln for m in _GENERIC_STATUS_MARKERS)]
    if not non_generic:
        return False
    # speaker-prefix-only («ترامپ:» alone) / too few meaningful Persian words
    words = [w for w in body.split() if len(w) > 1]
    persian_words = [w for w in words if any("؀" <= ch <= "ۿ" for ch in w)]
    if len(persian_words) < 4:
        return False
    from app.verification.gates import is_valid_headline
    return is_valid_headline(lines[0][:140]) or len(persian_words) >= 6


def to_telegram_html(text: str) -> str:
    """Convert our **bold** markers to <b>, escape everything else (no raw ** ever)."""
    import html as _h
    parts = []
    for i, seg in enumerate((text or "").split("**")):
        seg = _h.escape(seg)
        parts.append(("<b>%s</b>" % seg) if i % 2 == 1 else seg)
    return "".join(parts)


class TelegramBotPublisher:
    platform = "telegram"

    def __init__(self, bot_token: str, chat_id: str,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.bot_uid = bot_token.split(":", 1)[0] if ":" in bot_token else ""
        self.base = f"https://api.telegram.org/bot{bot_token}"
        self.transport = transport

    async def _api(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
                resp = await client.post(f"{self.base}/{method}", json=payload)
            return resp.json()
        except httpx.HTTPError as e:
            return {"ok": False, "description": f"transport: {e}"}

    async def get_chat(self, chat_id: str) -> dict[str, Any]:
        return await self._api("getChat", {"chat_id": chat_id})

    async def chat_member(self, chat_id: str, user_id: str) -> dict[str, Any]:
        return await self._api("getChatMember", {"chat_id": chat_id, "user_id": user_id})

    async def validate_publish_target(self) -> dict[str, Any]:
        """Public news target MUST be a channel with bot admin/post rights.
        A private chat is REFUSED — no silent fallback anywhere."""
        data = await self.get_chat(self.chat_id)
        if not data.get("ok"):
            return {"valid": False, "reason": f"getChat failed: {data.get('description', '?')}"}
        chat = data["result"]
        if chat.get("type") != "channel":
            return {"valid": False, "reason": f"destination type is {chat.get('type')}, not channel"}
        member = await self.chat_member(chat["id"], self.bot_uid)
        if not member.get("ok"):
            return {"valid": False, "reason": "bot membership not resolvable"}
        st = member["result"].get("status")
        can_post = member["result"].get("can_post_messages")
        if st != "administrator" or can_post is False:
            return {"valid": False, "reason": f"bot is '{st}', can_post_messages={can_post}"}
        return {"valid": True, "chat_id": chat["id"], "title": chat.get("title"),
                "username": chat.get("username")}

    async def send_message(self, text: str) -> dict[str, Any]:
        if not publisher_language_gate(text):
            return {"ok": False, "error": "BLOCKED_LANGUAGE_GATE"}
        data = await self._api("sendMessage", {
            "chat_id": self.chat_id, "text": to_telegram_html(text)[:4096], "parse_mode": "HTML",
            "disable_web_page_preview": True})
        if data.get("ok"):
            return {"ok": True, "message_id": data["result"]["message_id"]}
        return {"ok": False, "error": f"telegram: {data.get('description', '?')}"}

    async def send_media(self, path, caption, video=False):
        """sendPhoto/sendVideo with Persian newsroom caption (one coherent post)."""
        import os as _os
        if not publisher_language_gate(caption):
            return {"ok": False, "error": "BLOCKED_LANGUAGE_GATE"}
        # Markdown markers must NEVER reach Telegram (owner screenshot regression):
        # clip raw text (never splitting a ** pair), then convert to HTML.
        cap = caption or ""
        if len(cap) > 1020:
            cap = cap[:1020]
            if cap.count("**") % 2:
                cap = cap.rsplit("**", 1)[0].rstrip()
        field = 'video' if video else 'photo'
        try:
            fh = open(path, 'rb')
        except OSError as e:
            return {'ok': False, 'error': 'cache: %s' % e}
        try:
            async with httpx.AsyncClient(timeout=120, transport=self.transport) as client:
                resp = await client.post(
                    '%s/%s' % (self.base, 'sendVideo' if video else 'sendPhoto'),
                    data={'chat_id': self.chat_id, 'caption': to_telegram_html(cap), 'parse_mode': 'HTML'},
                    files={field: (_os.path.basename(path), fh)})
            data = resp.json()
        finally:
            fh.close()
        if data.get('ok'):
            return {'ok': True, 'message_id': data['result']['message_id']}
        return {'ok': False, 'error': 'telegram: %s' % data.get('description', '?')}


    async def edit_message(self, message_id: str, text: str) -> dict[str, Any]:
        if not publisher_language_gate(text):
            return {"ok": False, "error": "BLOCKED_LANGUAGE_GATE"}
        try:
            payload = {"chat_id": self.chat_id, "message_id": int(message_id),
                       "text": to_telegram_html(text)[:4096], "parse_mode": "HTML",
                       "disable_web_page_preview": True}
        except ValueError:
            return {"ok": False, "error": "bad message id"}
        data = await self._api("editMessageText", payload)
        if data.get("ok"):
            return {"ok": True}
        # MEDIA-EDIT: stories published via sendPhoto (branded cards) have a
        # CAPTION, not text — editMessageText rejects them ("no text in the
        # message to edit"). Retry once with editMessageCaption.
        if "no text in the message" in str(data.get("description", "")).lower():
            cap = text[:1020]
            if cap.count("**") % 2:
                cap = cap.rsplit("**", 1)[0].rstrip()
            data = await self._api("editMessageCaption", {
                "chat_id": self.chat_id, "message_id": int(message_id),
                "caption": to_telegram_html(cap), "parse_mode": "HTML"})
            if data.get("ok"):
                return {"ok": True}
        return {"ok": False, "error": f"telegram: {data.get('description', '?')}"}


def telegram_text_for_story(draft: dict[str, Any], signature: str) -> str:
    lines = [draft.get("headline", "")]
    lead = draft.get("lead", "").strip()
    if lead:
        lines += ["", lead]
    for p in draft.get("platform_variants", {}).get("telegram", "").split("\n"):
        if p.strip():
            lines += ["", p.strip()]
            break
    uncertain = draft.get("uncertain_facts") or []
    if uncertain:
        lines += ["", "هنوز تأیید نشده: " + "؛ ".join(uncertain[:3])]
    if signature:
        lines += ["", signature]
    return "\n".join(lines)


def persian_ratio(text: str) -> float:
    """Share of letters that are Persian-script (fa vs ar share the block)."""
    import re as _r
    letters = [c for c in (text or "") if c.isalpha()]
    if not letters:
        return 1.0
    fa = sum(1 for c in letters if "؀" <= c <= "ۿ")
    return fa / len(letters)


_PERSIAN_ONLY_LETTERS = set("پچژگ")


_ARABIC_ONLY = set("يكة")  # ي ك ة only — forms NEVER valid in Persian
_HEBREW = range(0x05D0, 0x05F0)
_AR_STOP = ("في", "من", "على", "عن", "أن", "الى", "التي", "الذي", "هذا", "هذه", "مع", "قد", "لا", "ما")
_FOOTER_MARKS = ("راسته؟", "@RastehNews", "🆔")


def story_content_language_check(text: str) -> bool:
    """CONTENT-level Persian check (§5/§6): strip footer/source/URLs/handles first,
    then reject Arabic morphology (ي/ك/ة...), Arabic stopwords, Hebrew, Latin-dominant."""
    import re as _r

    lines = []
    for ln in (text or "").split(chr(10)):
        t = ln.strip()
        if not t:
            continue
        if any(m in t for m in _FOOTER_MARKS) or t.startswith(("منبع:", "منابع:", "—")):
            continue
        t = _r.sub(r"https?://\S+|t\.me/\S+|@[A-Za-z0-9_]{3,}", " ", t)
        t = _r.sub(r"[🀀-🫿‌‏‎*#]+", " ", t)
        if t.strip():
            lines.append(t.strip())
    content = " ".join(lines)
    if not content:
        return False
    words = content.split()
    if not words:
        return False
    if any(ch in _ARABIC_ONLY for ch in content):
        return False
    ar_stop_hits = sum(1 for w in words if w in _AR_STOP)
    if ar_stop_hits >= max(1, len(words) // 8):
        return False
    heb = sum(1 for ch in content if ord(ch) in _HEBREW)
    if heb >= 2:
        return False
    letters = [c for c in content if c.isalpha()]
    if not letters:
        return False
    fa = sum(1 for c in letters if "؀" <= c <= "ۿ")
    lat = sum(1 for c in letters if c.isascii() and c.isalpha())
    if lat / len(letters) > 0.3:
        return False
    return fa / len(letters) >= 0.6


def is_persian_public_text(text: str) -> bool:
    """Backward-compatible alias: content-level check (footer cannot fool it)."""
    return story_content_language_check(text)


def publisher_language_gate(text: str) -> bool:
    """LAST-CHANCE fail-closed gate before ANY public API call."""
    return story_content_language_check(text)


_PERSIAN_ONLY_LETTERS = set("پچژگ")


_TOPIC_EMOJI = [
    ("WAR_MILITARY", "\U0001F396"), ("INTERNET", "\U0001F310"), ("CURRENCY", "\U0001F4B5"),
    ("DIPLOMACY", "\U0001F3DB"), ("IRAN_IRAQ", "\U0001F30D"), ("ECONOMY", "\U0001F4CA"),
]


def topic_emoji(text):
    from app.verification.gates import classify_priority

    topic, _ = classify_priority(text or "")
    for name, e in _TOPIC_EMOJI:
        if name == topic:
            return e
    return ""


def _resembles(headline, body, threshold=0.65):
    hset = set((headline or "").lower().split())
    bset = set((body or "").lower().split())
    if not hset:
        return False
    return len(hset & bset) / max(1, len(hset | bset)) >= threshold


def body_quality_gate(headline, body):
    """PUBLIC_BODY_QUALITY_GATE: no fragments/one-word/duplicate-of-headline bodies.
    Returns (ok, mode) where mode in {"ok", "compact"} — compact = headline-only post."""
    h = (headline or "").strip().strip("*").strip()
    b = (body or "").strip()
    if not h:
        return False, "no headline"
    if _resembles(h, b):
        return True, "compact"
    body_no_head = b.replace(h, "").strip()
    words = [w for w in body_no_head.split() if len(w) > 1]
    if len(words) < 4:
        return False, "body too short/fragment"
    return True, "ok"
