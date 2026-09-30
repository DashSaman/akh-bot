"""Telegram channel publisher (Bot API). Idempotent via the publication ledger.

Process restart must never repost old news: sent payloads are recognized by
(story_id, platform, payload_hash) before any API call.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("akh.pub.telegram")


class TelegramBotPublisher:
    platform = "telegram"

    def __init__(self, bot_token: str, chat_id: str,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base = f"https://api.telegram.org/bot{bot_token}"
        self.transport = transport

    async def send_message(self, text: str) -> dict[str, Any]:
        """Returns {ok, message_id?, error?} — never raises for API-level failures."""
        try:
            async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
                resp = await client.post(
                    f"{self.base}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": text[:4096],
                        "disable_web_page_preview": True,
                    },
                )
            data = resp.json()
        except httpx.HTTPError as e:
            return {"ok": False, "error": f"transport: {e}"}
        if data.get("ok"):
            return {"ok": True, "message_id": data["result"]["message_id"]}
        return {"ok": False, "error": f"telegram: {data.get('description', resp.status_code)}"}

    async def edit_message(self, message_id: str, text: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
                resp = await client.post(
                    f"{self.base}/editMessageText",
                    json={
                        "chat_id": self.chat_id,
                        "message_id": int(message_id),
                        "text": text[:4096],
                        "disable_web_page_preview": True,
                    },
                )
            data = resp.json()
        except httpx.HTTPError as e:
            return {"ok": False, "error": f"transport: {e}"}
        if data.get("ok"):
            return {"ok": True}
        return {"ok": False, "error": f"telegram: {data.get('description', resp.status_code)}"}


def telegram_text_for_story(draft: dict[str, Any], signature: str) -> str:
    """Telegram variant: complete but compact; evidence-aware signature."""
    lines = [draft.get("headline", "")]
    lead = draft.get("lead", "").strip()
    if lead:
        lines += ["", lead]
    for p in draft.get("platform_variants", {}).get("telegram", "").split("\n"):
        if p.strip():
            lines += ["", p.strip()]
            break  # telegram variant is pre-written; body stays on the website
    uncertain = draft.get("uncertain_facts") or []
    if uncertain:
        lines += ["", "هنوز تأیید نشده: " + "؛ ".join(uncertain[:3])]
    if signature:
        lines += ["", signature]
    return "\n".join(lines)
