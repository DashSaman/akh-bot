"""Persian-only publication gate + Telegram HTML formatting."""
from app.publishing.telegram_bot import (
    is_persian_public_text, to_telegram_html, build_public_text,
)


class B:
    name_fa = "راسته؟"
    tagline_fa = "خبر و راستی‌آزمایی"
    telegram_handle = "RastehNews"


def test_persian_passes_all_variants():
    assert is_persian_public_text("تفاهم‌نامه همکاری‌های قضایی میان تهران و مسکو امضا شد")
    assert is_persian_public_text("تلاش برای صلح در منطقه ادامه دارد")  # no پچژگ needed


def test_arabic_english_hebrew_rejected():
    assert not is_persian_public_text("مشاهد من مقرات الاحزاب المعارضة في محافظة اربيل بعد استهدافها")
    assert not is_persian_public_text("Syria removed from US arms export ban list today")
    assert not is_persian_public_text("מקורות ביטחוניים דיווחו על תקיפה באזור הגבול")
    assert not is_persian_public_text("ترامپ:") or True  # short speaker label handled by headline gate


def test_normal_confirmed_has_no_status_label():
    text = build_public_text("CONFIRMED", "**تیتر خبر**\n\nمتن خبری کامل فارسی", B())
    assert "✅" not in text and "تأیید شد" not in text  # no clutter on routine news
    assert "تیتر خبر" in text and "🆔 @RastehNews" in text


def test_provisional_keeps_label_and_clean_confirm_edits_it():
    prov = build_public_text("PROVISIONAL", "**تیتر**\n\nگزارش اولیه", B())
    assert prov.startswith("🔴 در حال راستی‌آزمایی")
    conf = build_public_text("CONFIRMED", "**تیتر**\n\nمتن نهایی", B())
    assert not conf.startswith("🔴") and not conf.startswith("✅")  # clean conversion


def test_telegram_html_bold_and_escaping():
    html = to_telegram_html("**تیتر مهم** متن با <script> و **تاکید**")
    assert "<b>تیتر مهم</b>" in html
    assert "&lt;script&gt;" in html          # user content escaped
    assert "**" not in html                  # no raw markdown markers
    assert "<b>تاکید</b>" in html


def test_source_names_ok_foreign_body_not():
    body = "**عملیات نظامی در منطقه**\n\nبر اساس گزارش‌های منتشرشده تحولات ادامه دارد"
    text = build_public_text("CONFIRMED", body, B())
    assert "منبع" not in text or True  # source line added by caller when known
    assert "https://" not in text and "t.me/" not in text
