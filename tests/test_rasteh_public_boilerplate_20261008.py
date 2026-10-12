"""Real Rasteh #1578 and #1575 source-channel contamination regressions."""
from types import SimpleNamespace
from app.publishing.telegram_bot import build_public_text, strip_boilerplate


_BRAND = SimpleNamespace(name_fa="راسته؟", tagline_fa="خبر و راستی‌آزمایی", telegram_handle="RastehNews")


def test_1578_removes_foreign_channel_promo_but_keeps_news():
    raw = (
        "زاکانی: نخستین محموله اتوبوس‌های مترو پس از عبور از محاصره وارد ایران شد\n"
        "✅ با ما اخبار جنگی بروز باشید\n@russiamilitery"
    )
    public = build_public_text("PROVISIONAL", raw, _BRAND, source_names="اخبار جنگ ایران و آمریکا")
    assert "زاکانی:" in public
    assert "نخستین محموله" in public
    assert "با ما اخبار جنگی" not in public
    assert "@russiamilitery" not in public


def test_1575_removes_source_commentary_but_keeps_oil_data():
    raw = (
        "ترامپ در تروث: «انتقال نفت به سطح پیش از جنگ بازگشت!»\n"
        "حجم انتقال نفت خام از منطقه خلیج فارس\n"
        "یاشار: چنل های بی سواد همه اینو زدن قیمت نفت 😂 😂 😂"
    )
    public = build_public_text("PROVISIONAL", raw, _BRAND, source_names="یاشار")
    assert "ترامپ در تروث" in public
    assert "حجم انتقال نفت خام" in public
    assert "چنل های بی سواد" not in public


def test_legitimate_news_about_channels_not_stripped():
    text = "مقام وزارت ارتباطات گفت کانال‌های خبری درباره قیمت نفت گزارش داده‌اند."
    assert strip_boilerplate(text) == text
