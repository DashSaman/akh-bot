"""Regression: V2 translated lead/context must reach the Telegram public copy."""
from app.newsroom.story_evolution import render_v2_public_text
from app.publishing.telegram_bot import public_body_is_substantive


class Brand:
    name_fa = "راسته؟"
    tagline_fa = "خبر و راستی‌آزمایی"
    telegram_handle = "RastehNews"


def test_translated_v2_lead_is_not_silently_dropped():
    content = {
        "headline": "پاسخ یمن آغاز شد",
        "lead": "گزارش منبع از آغاز پاسخ یمن خبر می‌دهد و جزئیات بیشتری درباره رویداد ارائه می‌کند.",
        "details": [],
        "lifecycle": "PROVISIONAL",
        "translated": True,
    }
    out = render_v2_public_text(content, Brand(), "نایا")
    assert "پاسخ یمن آغاز شد" in out
    assert content["lead"] in out
    assert "منبع: نایا" in out
    assert public_body_is_substantive(out)


def test_empty_lead_keeps_existing_renderer_shape():
    content = {
        "headline": "وزارت خارجه ایران سفیر بریتانیا را احضار کرد",
        "lead": "",
        "details": [],
        "lifecycle": "PROVISIONAL",
    }
    out = render_v2_public_text(content, Brand(), "نایا")
    assert "وزارت خارجه ایران سفیر بریتانیا را احضار کرد" in out
    assert "منبع: نایا" in out
