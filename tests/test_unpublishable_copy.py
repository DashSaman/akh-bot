import asyncio
import json

import httpx
import pytest

from app.db.repo import PublicationsRepo, StoriesRepo, utcnow
from app.jobs.runner import make_edit_handler, make_publish_handler, make_send_handler
from app.newsroom.quality_gates import publication_quality_gate
from app.newsroom.translator import translate_event
from app.publishing.telegram_bot import TelegramBotPublisher, public_body_is_substantive


NOTICE = "⚠️ این خبر به‌دلیل اشکال در ترجمه موقتاً در حال بازبینی است."
RADIO = "📻 تازه‌ترین خبرهای ایران و جهان، یکشنبه ۱۷ آبان ۱۴۰۵ از رادیو بی‌بی‌سی در لندن"
GOOD = "وزارت خارجه ایران اعلام کرد مذاکرات در تهران ادامه دارد."


@pytest.mark.parametrize("text", [NOTICE, "خطای ترجمه: دریافت پاسخ از سرویس ناموفق بود.",
    "متأسفم، نمی‌توانم متن ارائه‌شده را ترجمه کنم. لطفاً دوباره تلاش کنید.", RADIO])
def test_internal_notices_and_media_announcements_are_not_news(db, text):
    assert not public_body_is_substantive(text)
    assert publication_quality_gate(db, text, "", 100) is not None


@pytest.mark.parametrize("method", ["send_message", "send_media", "send_media_ref", "edit_message"])
def test_every_telegram_boundary_blocks_failure_notices(method, tmp_path):
    requests=[]
    def api(request):
        requests.append(request)
        return httpx.Response(200,json={"ok":True,"result":{"message_id":42}})
    publisher=TelegramBotPublisher("TEST","@test",transport=httpx.MockTransport(api))
    if method=="send_media_ref": call=publisher.send_media_ref({"file_id":"existing"},NOTICE)
    elif method=="send_media": call=publisher.send_media(str(tmp_path/'missing.jpg'),NOTICE)
    elif method=="edit_message": call=publisher.edit_message("42",NOTICE)
    else: call=publisher.send_message(NOTICE)
    assert asyncio.run(call)["ok"] is False
    assert requests == []


@pytest.mark.parametrize("handler_factory", [make_send_handler,make_edit_handler,make_publish_handler])
def test_old_queued_notices_are_skipped_without_api_calls(db,settings,handler_factory):
    db.execute("INSERT INTO events(title,status,first_seen_at,last_seen_at) VALUES(?,'NEW',?,?)",(GOOD,utcnow(),utcnow()))
    sid=StoriesRepo(db).create(1,GOOD,"",{"headline":GOOD,"lead":"","details":[]})
    if handler_factory is make_edit_handler:
        p=PublicationsRepo(db).upsert(sid,"telegram","old",1)
        PublicationsRepo(db).mark(p,"SENT",remote_id="42")
    calls=[]
    def factory():
        calls.append(True)
        raise AssertionError("unpublishable payload reached publisher")
    h=handler_factory(db,settings,factory)
    assert asyncio.run(h({"story_id":sid,"platform":"telegram","payload_hash":"notice","text":NOTICE}))
    row=db.query_one("SELECT * FROM publications WHERE payload_hash='notice'")
    assert row["status"] == "SKIPPED"
    assert calls == []


def test_duplicate_done_notice_keeps_original_sent_ledger(db,settings):
    db.execute("INSERT INTO events(title,status,first_seen_at,last_seen_at) VALUES(?,'NEW',?,?)",(GOOD,utcnow(),utcnow()))
    sid=StoriesRepo(db).create(1,GOOD,"",{"headline":GOOD})
    p=PublicationsRepo(db).upsert(sid,"telegram","notice",1)
    PublicationsRepo(db).mark(p,"SENT",remote_id="42")
    h=make_send_handler(db,settings,lambda:None)
    assert asyncio.run(h({"story_id":sid,"platform":"telegram","payload_hash":"notice","text":NOTICE}))
    row=db.query_one("SELECT * FROM publications WHERE id=?",(p,))
    assert row["status"] == "SENT"
    assert row["remote_id"] == "42"


@pytest.mark.parametrize("cached", [False,True])
def test_translator_rejects_failure_prose_in_fresh_and_cached_results(db,cached):
    class Router:
        available=True
        async def chat_json(self,**kwargs):
            return {"headline":"خطای ترجمه", "lead":"ترجمه این متن به دلیل مشکل سرویس امکان پذیر نیست."}
    if cached:
        from app.db.repo import LlmCacheRepo
        from app.newsroom.translator import _cache_key,TRANSLATE_VERSION
        LlmCacheRepo(db).put(_cache_key("en","Talks continue","Talks continue"),
            json.dumps({"headline":"خطای ترجمه", "lead":"ترجمه این متن به دلیل مشکل سرویس امکان پذیر نیست."}),
            "test",TRANSLATE_VERSION,0,0,0)
    assert asyncio.run(translate_event(Router(),"Talks continue","Talks continue",db=db,source_language="en")) is None


@pytest.mark.parametrize("text", [GOOD,
    "یوسف جبارین در مصاحبه گفت: نمی‌توانم مسئولیت اقدامات نظامی علیه مردم فلسطین را بپذیرم.",
    "خطای ترجمه سخنان رئیس‌جمهور ایران باعث اعتراض وزارت خارجه شد.",
    "متأسفانه بارش شدید باران در تهران باعث آب‌گرفتگی خیابان‌ها شد."])
def test_real_news_and_attributed_quotes_remain_publishable(text):
    assert public_body_is_substantive(text)
