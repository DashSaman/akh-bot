import json

import httpx
import pytest

from app.db.repo import RawItemsRepo, SourcesRepo
from app.ingestion.rss import fetch_rss_source

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>تست</title>
<item><title>حمله موشکی به شهر ساحلی</title><link>https://n.example/1?utm_source=tg</link>
<pubDate>Wed, 30 Sep 2026 10:00:00 GMT</pubDate><description>منابع محلی از شنیده شدن صدای انفجار خبر می‌دهند.</description></item>
<item><title>اجلاس سران</title><link>https://n.example/2</link>
<pubDate>Wed, 30 Sep 2026 11:00:00 GMT</pubDate><description>اجلاس فردا برگزار می‌شود.</description></item>
</channel></rss>"""


def _source(db, status="APPROVED"):
    return SourcesRepo(db).create(name="فید تست", platform="rss", url="https://n.example/feed",
                                  status=status)


@pytest.mark.asyncio
async def test_rss_fetch_and_store(db):
    sid = _source(db)
    source = SourcesRepo(db).get(sid)
    summary = await fetch_rss_source(source, db, parse_only=FEED.encode())
    assert summary["new"] == 2
    items = RawItemsRepo(db).list()
    assert len(items) == 2
    # refetch → all skipped (idempotent)
    source = SourcesRepo(db).get(sid)
    summary = await fetch_rss_source(source, db, parse_only=FEED.encode())
    assert summary["new"] == 0 and summary["skipped"] == 2


@pytest.mark.asyncio
async def test_rss_invalid_xml_records_error(db):
    sid = _source(db)
    source = SourcesRepo(db).get(sid)
    summary = await fetch_rss_source(source, db, parse_only=b"<html><body>not a feed")
    assert summary.get("error") == "invalid XML"
    row = SourcesRepo(db).get(sid)
    assert row["last_error"] and "invalid XML" in row["last_error"]
    assert row["health_score"] < 1.0  # reliability is a decaying signal


@pytest.mark.asyncio
async def test_rss_http_304_skips(db):
    sid = _source(db)
    SourcesRepo(db).db.execute("UPDATE sources SET fetch_state=? WHERE id=?",
                               (json.dumps({"etag": "W/\"x\""}), sid))
    source = SourcesRepo(db).get(sid)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(304, headers={"etag": "W/\"x\""})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        summary = await fetch_rss_source(source, db, client=client)
    assert summary["not_modified"] is True
    assert RawItemsRepo(db).list() == []


@pytest.mark.asyncio
async def test_rss_timeout_isolated(db):
    sid = _source(db)
    source = SourcesRepo(db).get(sid)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        summary = await fetch_rss_source(source, db, client=client)
    assert "error" in summary
    # collector survives: source marked with error, process intact
    assert SourcesRepo(db).get(sid)["last_error"]
