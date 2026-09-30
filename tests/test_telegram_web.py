"""Telegram t.me/s/ web-preview parser tests."""
import asyncio

from app.ingestion.telegram_web import fetch_telegram_web_source, parse_preview_page

PAGE = """<html><body>
<div class="tgme_widget_message_wrap">
<div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="withyashar/1234"">
<div class="tgme_widget_message_bubble">
  <div class="tgme_widget_message_text js-message_text" dir="auto">فارسی تست پیام<br/>خط دوم پیام</div>
  <div class="tgme_widget_message_footer"><time datetime="2026-09-30T15:00:00+00:00"></time></div>
</div></div></div>
<div class="tgme_widget_message_wrap">
<div class="tgme_widget_message js-widget_message" data-post="withyashar/1235"">
<div class="tgme_widget_message_bubble">
  <div class="tgme_widget_message_text js-message_text" dir="auto">English message about markets &amp; oil</div>
  <div class="tgme_widget_message_footer"><time datetime="2026-09-30T15:05:00+00:00"></time></div>
</div></div></div>
</body></html>"""


def test_parse_preview_page():
    msgs = parse_preview_page(PAGE)
    assert len(msgs) == 2
    assert msgs[0]["post"] == "withyashar/1234"
    assert "فارسی تست پیام" in msgs[0]["text"] and "خط دوم پیام" in msgs[0]["text"]
    assert msgs[0]["published"] == "2026-09-30T15:00:00+00:00"
    assert "markets & oil" in msgs[1]["text"]  # html entity decoded


def test_parse_empty_page():
    assert parse_preview_page("<html></html>") == []


def test_fetch_stores_items_once(db):
    from app.db.repo import RawItemsRepo, SourcesRepo

    sid = SourcesRepo(db).create(name="watch", platform="telegram", external_id="somechannel",
                                 status="APPROVED", source_type="telegram_web_preview",
                                 verification_allowed=False,
                                 source_role="AGGREGATOR", can_increase_independent_count=False)
    src = SourcesRepo(db).get(sid)

    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=PAGE)

    transport = httpx.MockTransport(handler)
    import app.ingestion.telegram_web as tgw

    orig_client = tgw.httpx.AsyncClient
    tgw.httpx.AsyncClient = lambda **kw: orig_client(transport=transport, **kw)
    try:
        s1 = asyncio.run(tgw.fetch_telegram_web_source(src, db))
        src = SourcesRepo(db).get(sid)
        s2 = asyncio.run(tgw.fetch_telegram_web_source(src, db))
    finally:
        tgw.httpx.AsyncClient = orig_client
    assert s1["new"] == 2 and s1["skipped"] == 0
    assert s2["new"] == 0 and s2["skipped"] == 2  # idempotent re-fetch
    rows = RawItemsRepo(db).list()
    assert rows[0]["activation_ok"] in (0, 1)  # guard applied by activated_at
    assert rows[0]["lineage_key"] == "tgweb:somechannel"
