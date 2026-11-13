"""Regressions for source attribution and lossless standalone news."""
from __future__ import annotations

import asyncio

import httpx

from app.newsroom.claim_model import extract_structured
from app.newsroom.quality_gates import context_incomplete
from app.newsroom.story_evolution import (
    build_v2_content, select_details, select_headline,
)
from app.publishing.telegram_bot import (
    TelegramBotPublisher, build_public_text, dedup_paragraphs,
)


class Brand:
    name_fa = "راسته؟"
    tagline_fa = "خبر و راستی‌آزمایی"
    telegram_handle = "RastehNews"


ORIGINAL = (
    "سازمان رادیو و تلویزیون اسرائیل: رئیس ستاد کل ارتش این کشور "
    "از انجام عملیات نظامی علیه ایران حمایت می‌کند، اما معتقد است "
    "این عملیات باید در زمان و به شیوه مناسب انجام شود."
)
ORPHAN = ORIGINAL.split(": ", 1)[1]


def test_screenshot_regression_preserves_media_name_and_country_context():
    claim = {**extract_structured(ORIGINAL, 1).to_dict(), "state": "UNVERIFIED"}
    headline = select_headline([claim])
    assert headline.startswith("سازمان رادیو و تلویزیون اسرائیل:")
    assert ORPHAN in headline
    assert not context_incomplete(headline)
    assert context_incomplete(ORPHAN)  # Iran is a TARGET, not the "this country" referent
    story = build_v2_content({}, [claim], max_details=5)
    assert story and story["headline"] == headline
    rendered = build_public_text(
        "PROVISIONAL", headline, Brand(), source_names="پایشار"
    )
    assert "سازمان رادیو و تلویزیون اسرائیل" in rendered
    assert "مناسب انجام شود." in rendered
    assert "منبع: پایشار" in rendered


def test_long_broadcast_agency_label_is_not_lost():
    original = (
        "سازمان رادیو و تلویزیون جمهوری اسلامی ایران: مسئولان این سازمان "
        "از تغییر زمان پخش برنامه‌های خبری در هفته آینده خبر دادند."
    )
    claim = {**extract_structured(original, 2).to_dict(), "state": "UNVERIFIED"}
    assert claim["actor"] == "سازمان رادیو و تلویزیون جمهوری اسلامی ایران"
    assert select_headline([claim]).startswith(claim["actor"] + ": ")


def test_speaker_label_is_retained_but_generic_breaking_label_is_not():
    original = "رئیس اداره راه: محورهای اصلی استان به دلیل بارش برف سنگین مسدود شده‌اند."
    c = {**extract_structured(original, 3).to_dict(), "state": "UNVERIFIED"}
    assert select_headline([c]).startswith("رئیس اداره راه:")
    emergency = "فوری: محورهای اصلی استان به دلیل بارش برف سنگین مسدود شده‌اند."
    c2 = {**extract_structured(emergency, 4).to_dict(), "state": "UNVERIFIED"}
    assert not select_headline([c2]).startswith("فوری:")


def test_each_distinct_detail_keeps_its_attribution():
    claims = [
        {"id": 1, "state": "UNVERIFIED",
         "actor": "خبرگزاری الف", "text": "وزارت کشور نتایج شمارش آرا را اعلام کرد."},
        {"id": 2, "state": "UNVERIFIED",
         "actor": "سازمان نظارت انتخابات", "text": "در دو حوزه بازشماری آرا در حال انجام است."},
    ]
    headline = select_headline(claims)
    details = select_details(claims, headline, 5)
    assert any("سازمان نظارت انتخابات:" in d for d in details)
    assert not any(d == headline for d in details)


def test_lexical_similarity_never_discards_a_change_in_meaning():
    first = "ارتش اسرائیل انجام عملیات نظامی علیه ایران را تأیید کرد."
    second = "ارتش اسرائیل انجام عملیات نظامی علیه ایران را تأیید نکرد."
    third = "ارتش ایران انجام عملیات نظامی علیه اسرائیل را تأیید کرد."
    output = dedup_paragraphs("\n".join([first, second, third, first]))
    assert output.splitlines() == [first, second, third]


def test_large_media_caption_preserves_full_text_as_text_only_post():
    calls = []

    def mock_send(request: httpx.Request):
        calls.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 55}})

    publisher = TelegramBotPublisher(
        "TEST_TOKEN", "@staging", transport=httpx.MockTransport(mock_send)
    )
    long_story = (
        "سازمان رادیو و تلویزیون اسرائیل گزارش داد که درباره اقدام نظامی علیه ایران بحث شده است. "
        * 15
    )
    assert len(long_story) > 1024
    result = asyncio.run(publisher.send_media_ref({"file_id": "photoid"}, long_story))
    assert result["ok"]
    assert len(calls) == 1
    assert calls[0].url.path.endswith("/sendMessage")
    assert calls[0].read().decode("utf-8").count("سازمان رادیو و تلویزیون اسرائیل") == 15


def test_overlong_text_is_held_instead_of_truncated():
    called = []

    def mock_send(request: httpx.Request):
        called.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 55}})

    publisher = TelegramBotPublisher(
        "TEST_TOKEN", "@staging", transport=httpx.MockTransport(mock_send)
    )
    text = "خبرگزاری تأیید کرد که متن اطلاعیه هنوز کامل منتشر نشده است. " * 90
    assert len(text) > 4096
    result = asyncio.run(publisher.send_message(text))
    assert result["error"] == "BLOCKED_TEXT_LENGTH"
    assert not called
