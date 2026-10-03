"""Owner-screenshot regressions: (1) raw Markdown `**` must never appear in
ANY Telegram payload (message, media caption, edit); (2) the broken branded
fallback card stays disabled until the new renderer passes fixtures."""
import asyncio

import httpx
import pytest

from app.db.repo import SourcesRepo, StoriesRepo, utcnow
from app.newsroom import v2_pipeline
from app.publishing.telegram_bot import TelegramBotPublisher

DRAFT = {
    "headline": "آزمون کارت",
    "lead": "لید آزمون",
    "platform_variants": {"telegram": "**تیتر آزمون** خبر تستی است"},
}


class _CaptureTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.requests = []
        self.bodies = []

    async def handle_async_request(self, request):
        self.requests.append(request)
        self.bodies.append(await request.aread())  # consume before file closes
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})


@pytest.fixture()
def story_with_media(db):
    SourcesRepo(db).create(name="s", platform="rss", url="u", status="APPROVED")
    db.execute("INSERT INTO events(title,status,first_seen_at,last_seen_at) "
               "VALUES('t','PUBLISHED',?,?)", (utcnow(), utcnow()))
    return StoriesRepo(db).create(1, "آزمون کارت", "لید", DRAFT)


# ---- §6: Markdown leakage --------------------------------------------------

async def test_send_media_caption_converts_markdown(tmp_path, story_with_media):
    transport = _CaptureTransport()
    pub = TelegramBotPublisher("TOK", "@stage", transport=transport)
    card = tmp_path / "c.png"
    card.write_bytes(b"\x89PNG\r\n\x1a\n")
    result = await pub.send_media(str(card),
                                  caption="**تیتر آزمون** خبر تستی است")
    assert result["ok"]
    body = transport.bodies[0]
    assert b"**" not in body, "raw Markdown leaked into sendPhoto payload"
    assert "<b>تیتر آزمون</b>".encode() in body


async def test_send_media_long_caption_never_splits_bold_pair(tmp_path, story_with_media):
    transport = _CaptureTransport()
    pub = TelegramBotPublisher("TOK", "@stage", transport=transport)
    card = tmp_path / "c.png"
    card.write_bytes(b"\x89PNG\r\n\x1a\n")
    filler = "خبر " * 400  # forces the 1020 clip with an odd ** tail
    caption = "**تیتر** " + filler + " **دُم"
    result = await pub.send_media(str(card), caption=caption)
    assert result["ok"]
    body = transport.bodies[0]
    assert b"**" not in body
    # converted HTML must be balanced (no truncated tag → Telegram 400)
    txt = body.decode("utf-8", "ignore")
    assert txt.count("<b>") == txt.count("</b>")


# ---- §5: broken fallback card disabled ------------------------------------

def test_broken_fallback_card_disabled_by_default(db, settings, story_with_media):
    assert settings.media_fallback_cards_enabled is False
    v2_pipeline._attach_event_media(db, settings, 1, story_with_media,
                                    "آزمون کارت", "PROVISIONAL")
    cards = db.query("SELECT COUNT(*) c FROM media_assets WHERE kind='card'")
    assert cards[0]["c"] == 0, "branded fallback card must stay OFF by default"


def test_fallback_card_flag_gates_registration(db, settings, story_with_media,
                                               monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "media_fallback_cards_enabled", True)
    monkeypatch.setattr("app.publishing.media.cache_dir",
                        lambda: str(tmp_path))
    v2_pipeline._attach_event_media(db, settings, 1, story_with_media,
                                    "آزمون کارت", "PROVISIONAL")
    cards = db.query("SELECT COUNT(*) c FROM media_assets WHERE kind='card'")
    assert cards[0]["c"] == 1
