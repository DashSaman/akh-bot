"""Breaking-news flow: destination validation, public copy policy,
same-message lifecycle edits, misdirected-chat re-routing, fan-out."""
import asyncio
import json

import httpx
import pytest

from app.core.textnorm import sha256_hex
from app.db.repo import EventsRepo, JobsRepo, PublicationsRepo, SettingsRepo, SourcesRepo, StoriesRepo
from app.jobs.runner import JobRunner, make_publish_handler
from app.publishing.telegram_bot import (
    TelegramBotPublisher, build_public_text, sanitize_public_copy,
)


class Brand:
    name_fa = "راسته؟"
    telegram_handle = "RastehNews"


class S:
    telegram_publish_target = "-1004459746525"
    max_posts_per_hour = 100
    max_posts_per_day = 100
    max_provisional_posts_per_hour = 100
    max_confirmed_posts_per_hour = 100
    telegram_publish_target = "-1004459746525"


# ---------- public copy policy ----------

def test_public_copy_hides_external_sources_and_adds_own_signature():
    body = "متن خبر بر اساس گزارش منتشرشده.\n\n📖 منبع: t.me/withyashar\nhttps://bbc.com/x — @somechannel"
    text = build_public_text("PROVISIONAL", body, Brand(), "hidden", True)
    assert text.startswith("🔴 **")
    assert "🆔 @RastehNews" in text
    assert "راسته؟" not in text.split("🆔")[-1]  # footer = handle ONLY
    assert "t.me/" not in text and "bbc.com" not in text and "@somechannel" not in text
    assert "منبع:" not in text
    assert "بر اساس گزارش منتشرشده" in text  # attribution words preserved


def test_public_copy_modes_names_only_vs_links():
    body = "متن\n📖 منبع: ایرنا https://isna.ir/x"
    assert "ایرنا" in sanitize_public_copy(body, "names_only", Brand())
    assert "isna.ir" not in sanitize_public_copy(body, "names_only", Brand())
    assert "isna.ir" in sanitize_public_copy(body, "links", Brand())


# ---------- destination validation ----------

@pytest.mark.asyncio
async def test_private_chat_refused_as_publish_target():
    def handler(request):
        return httpx.Response(200, json={"ok": True, "result": {
            "id": 5504556066, "type": "private", "first_name": "owner"}})

    pub = TelegramBotPublisher("8669:t", "5504556066", transport=httpx.MockTransport(handler))
    v = await pub.validate_publish_target()
    assert v["valid"] is False and "not channel" in v["reason"]


@pytest.mark.asyncio
async def test_channel_without_admin_rights_refused():
    def handler(request):
        if request.url.path.endswith("getChat"):
            return httpx.Response(200, json={"ok": True, "result": {
                "id": -1004459746525, "type": "channel", "title": "ch"}})
        return httpx.Response(200, json={"ok": True, "result": {
            "status": "member", "can_post_messages": False}})

    pub = TelegramBotPublisher("8669:t", "-1004459746525", transport=httpx.MockTransport(handler))
    v = await pub.validate_publish_target()
    assert v["valid"] is False and "can_post" in v["reason"]


@pytest.mark.asyncio
async def test_valid_channel_passes():
    def handler(request):
        if request.url.path.endswith("getChat"):
            return httpx.Response(200, json={"ok": True, "result": {
                "id": -1004459746525, "type": "channel", "title": "ch", "username": "RastehNews"}})
        return httpx.Response(200, json={"ok": True, "result": {
            "status": "administrator", "can_post_messages": True}})

    pub = TelegramBotPublisher("8669:t", "-1004459746525", transport=httpx.MockTransport(handler))
    v = await pub.validate_publish_target()
    assert v["valid"] is True and v["username"] == "RastehNews"


# ---------- same-message lifecycle edit + misdirected re-route ----------

def _story(db, lifecycle="PROVISIONAL"):
    SourcesRepo(db).create(name="s", platform="rss", url="u", status="APPROVED")
    db.execute("INSERT INTO events(title,status,first_seen_at,last_seen_at) VALUES('e','NEW','2030-01-01T00:00:00+00:00','2030-01-01T00:00:00+00:00')")
    sid = StoriesRepo(db).create(1, "خبر آزمون", "لید", {"platform_variants": {"telegram": "متن"}})
    db.execute("UPDATE stories SET lifecycle=? WHERE id=?", (lifecycle, sid))
    return sid


@pytest.mark.asyncio
async def test_provisional_to_confirmed_edits_same_message(db):
    story_id = _story(db)
    calls = {"send": 0, "edit": 0}

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("sendMessage"):
            calls["send"] += 1
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})
        if request.url.path.endswith("editMessageText"):
            calls["edit"] += 1
            body = json.loads(request.content)
            assert body["message_id"] == 42 and len(body["text"]) > 20
            return httpx.Response(200, json={"ok": True, "result": True})
        raise AssertionError(request.url.path)

    factory = lambda: TelegramBotPublisher("t", "-1004459746525", transport=httpx.MockTransport(transport))
    handler = make_publish_handler(db, S(), factory)
    p1 = {"story_id": story_id, "platform": "telegram", "payload_hash": sha256_hex("v1"),
          "text": "🔴 در حال راستی‌آزمایی\n\nمتن\n\n🆔 @RastehNews"}
    assert await handler(p1) is True
    StoriesRepo(db).set_lifecycle(story_id, "CONFIRMED", "confirmed by second source",
                                  {"platform_variants": {"telegram": "متن"}})
    p2 = dict(p1, payload_hash=sha256_hex("v2"),
                  text="تأیید این خبر با منبع دوم مستقل انجام شد و متن نهایی بازنویسی گردید")
    assert await handler(p2) is True
    assert calls == {"send": 1, "edit": 1}  # SAME message updated, no duplicate
    rows = PublicationsRepo(db).list()
    assert len(rows) == 2 and all(r["status"] == "SENT" for r in rows)
    assert rows[0]["remote_id"] == "42" and rows[1]["remote_id"] == "42"
    assert rows[0]["chat_id"] == "-1004459746525"


@pytest.mark.asyncio
async def test_misdirected_private_chat_delivery_reroutes_to_channel(db):
    """Old SENT row in the WRONG chat must not hijack the edit path."""
    story_id = _story(db)
    pubs = PublicationsRepo(db)
    legacy = pubs.upsert(story_id, "telegram", sha256_hex("old"), 1)
    pubs.mark(legacy, "SENT", remote_id="4")
    db.execute("UPDATE publications SET chat_id='5504556066' WHERE id=?", (legacy,))
    sent = {"n": 0}

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("sendMessage"):
            body = json.loads(request.content)
            assert body["chat_id"] == "-1004459746525"
            sent["n"] += 1
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 77}})
        raise AssertionError(request.url.path)

    factory = lambda: TelegramBotPublisher("t", "-1004459746525", transport=httpx.MockTransport(transport))
    handler = make_publish_handler(db, S(), factory)
    ok = await handler({"story_id": story_id, "platform": "telegram",
                        "payload_hash": sha256_hex("new"), "text": "نسخه بازنویسی‌شده خبر با جزئیات تازه منتشر شد"})
    assert ok is True and sent["n"] == 1  # NEW channel post; private row untouched


# ---------- fan-out policy ----------

def test_distribution_plan_confirmed_vs_provisional():
    from app.publishing.fanout import distribution_plan

    class Cfg:
        telegram_publish_ready = True
        public_base_url = ""

    class Repo:
        def is_paused(self, platform=None):
            return False

    assert distribution_plan("CONFIRMED", Cfg(), Repo()) == ["telegram", "website_preview"]
    assert distribution_plan("PROVISIONAL", Cfg(), Repo()) == ["telegram"]
