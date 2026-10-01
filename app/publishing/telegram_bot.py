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
    if lines:
        first = lines[0].strip()
        bolded = first if first.startswith("**") else "**" + first + "**"
        lines[0] = (icon + " " + bolded).strip() if icon else bolded
        clean = chr(10).join(lines)
    src = ("منبع: " + source_names) if source_names else ""
    sig = brand_signature(brand, signature_enabled)
    parts = [p for p in (clean, src, sig) if p]
    return (chr(10) + chr(10)).join(parts)


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
        data = await self._api("sendMessage", {
            "chat_id": self.chat_id, "text": to_telegram_html(text)[:4096], "parse_mode": "HTML",
            "disable_web_page_preview": True})
        if data.get("ok"):
            return {"ok": True, "message_id": data["result"]["message_id"]}
        return {"ok": False, "error": f"telegram: {data.get('description', '?')}"}

    async def edit_message(self, message_id: str, text: str) -> dict[str, Any]:
        try:
            payload = {"chat_id": self.chat_id, "message_id": int(message_id),
                       "text": to_telegram_html(text)[:4096], "parse_mode": "HTML",
                       "disable_web_page_preview": True}
        except ValueError:
            return {"ok": False, "error": "bad message id"}
        data = await self._api("editMessageText", payload)
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


_ARABIC_ONLY_LETTERS = set("يكةآ")  # ي ك ة — Arabic-specific forms


def is_persian_public_text(text: str) -> bool:
    """LANGUAGE GATE: public text must be Persian.
    - Arabic script w/o any Persian-exclusive letter + Arabic-only forms → reject
    - Latin/Hebrew/etc paragraphs fail the ratio gate
    Persian may legitimately lack پچژگ, but then it must also lack Arabic ي/ك/ة."""
    if not text or not text.strip():
        return False
    if persian_ratio(text) < 0.55:
        return False
    has_persian_excl = any(c in _PERSIAN_ONLY_LETTERS for c in text)
    has_arabic_only = any(c in _ARABIC_ONLY_LETTERS for c in text)
    if has_arabic_only and not has_persian_excl:
        return False  # raw Arabic
    return True


def to_telegram_html(text: str) -> str:
    """Convert our **bold** markers to <b>, escape everything else (no raw ** ever)."""
    import html as _h
    parts = []
    for i, seg in enumerate((text or "").split("**")):
        seg = _h.escape(seg)
        parts.append(("<b>%s</b>" % seg) if i % 2 == 1 else seg)
    return "".join(parts)
