"""MEDIA-EDIT regression: lifecycle edits of sendPhoto messages must fall
back to editMessageCaption when Telegram rejects editMessageText with
"there is no text in the message to edit" (introduced by branded cards)."""
from __future__ import annotations

import json

import httpx
import pytest

from app.publishing.telegram_bot import TelegramBotPublisher


@pytest.mark.asyncio
async def test_edit_message_media_falls_back_to_caption():
    calls = []

    async def transport(request: httpx.Request) -> httpx.Response:
        await request.aread()
        calls.append((request.url.path, json.loads(request.content)))
        if request.url.path.endswith("editMessageText"):
            return httpx.Response(200, json={
                "ok": False,
                "description": "Bad Request: there is no text in the message to edit",
            })
        if request.url.path.endswith("editMessageCaption"):
            return httpx.Response(200, json={"ok": True, "result": True})
        raise AssertionError(request.url.path)

    pub = TelegramBotPublisher("t", "-100chat", transport=httpx.MockTransport(transport))
    result = await pub.edit_message("77", "🔴 **عنوان**\n\nمتن فارسی آزمون برای ویرایش\n\n🆔 @RastehNews")
    assert result["ok"] is True
    assert len(calls) == 2
    path, body = calls[1]
    assert path.endswith("editMessageCaption")
    assert body["message_id"] == 77
    assert "<b>" in body["caption"] and "**" not in body["caption"]


@pytest.mark.asyncio
async def test_edit_message_text_success_no_fallback():
    calls = []

    async def transport(request: httpx.Request) -> httpx.Response:
        await request.aread()
        calls.append(request.url.path)
        return httpx.Response(200, json={"ok": True, "result": True})

    pub = TelegramBotPublisher("t", "-100chat", transport=httpx.MockTransport(transport))
    result = await pub.edit_message("78", "متن فارسی ویرایش موفق")
    assert result["ok"] is True
    assert len(calls) == 1 and calls[0].endswith("editMessageText")


@pytest.mark.asyncio
async def test_edit_message_caption_truncates_without_dangling_markers():
    calls = []

    async def transport(request: httpx.Request) -> httpx.Response:
        await request.aread()
        calls.append(json.loads(request.content))
        if request.url.path.endswith("editMessageText"):
            return httpx.Response(200, json={
                "ok": False,
                "description": "Bad Request: there is no text in the message to edit",
            })
        return httpx.Response(200, json={"ok": True, "result": True})

    pub = TelegramBotPublisher("t", "-100chat", transport=httpx.MockTransport(transport))
    long_text = "🔴 **" + "متن بلند " * 300 + "**\n\n🆔 @RastehNews"
    result = await pub.edit_message("79", long_text)
    assert result["ok"] is True
    cap = calls[-1]["caption"]
    assert len(cap) <= 1024
    assert cap.count("<b>") == cap.count("</b>")  # no dangling bold from truncation
