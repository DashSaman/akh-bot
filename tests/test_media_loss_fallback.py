"""MEDIA-LOSS regression (2026-10-04): a missing card file must degrade to
TEXT-ONLY publish — never fail the story, never publish a broken image."""
from __future__ import annotations

import json

import httpx
import pytest

from app.publishing.telegram_bot import TelegramBotPublisher


@pytest.mark.asyncio
async def test_send_media_missing_file_falls_back_to_text():
    calls = []

    async def transport(request: httpx.Request) -> httpx.Response:
        await request.aread()
        calls.append(request.url.path)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 5}})

    pub = TelegramBotPublisher("t", "-100chat", transport=httpx.MockTransport(transport))
    result = await pub.send_media("/nonexistent/media/card-v2-123.png",
                                  "🔴 **عنوان خبر**\n\nمتن کامل خبر فارسی\n\n🆔 @RastehNews")
    assert result["ok"] is True
    assert len(calls) == 1 and calls[0].endswith("sendMessage")
    assert result.get("message_id") == 5
