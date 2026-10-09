"""Regression: Telegram public formatting must not leak preview brand or repeated lead."""
from types import SimpleNamespace
from app.publishing.telegram_bot import build_public_text

BRAND = SimpleNamespace(name_fa="راسته؟", tagline_fa="خبر و راستی‌آزمایی", telegram_handle="RastehNews")


def test_truncated_headline_same_as_lead_is_not_repeated():
    headline = "مقام آمریکایی گفت حملات برنامه‌ریزی‌شده به ایران در آخرین لحظه…"
    lead = "مقام آمریکایی گفت حملات برنامه‌ریزی‌شده به ایران در آخرین لحظه به تعویق افتاد و نیروها در حال آماده‌باش باقی ماندند."
    rendered = build_public_text("PROVISIONAL", headline + "\n\n" + lead, BRAND, source_names="العربیه")
    assert rendered.count("مقام آمریکایی گفت حملات برنامه‌ریزی‌شده") == 1
    assert "به تعویق افتاد" in rendered
    assert rendered.endswith("🆔 @RastehNews")


def test_exact_duplicate_lead_is_not_repeated():
    text = "گزارش جدید درباره وضعیت منطقه منتشر شد و منابع در حال بررسی آن هستند."
    rendered = build_public_text("PROVISIONAL", text + "\n\n" + text, BRAND, source_names="الجزیره")
    assert rendered.count(text) == 1


def test_correct_config_brand_used_for_public_footer(tmp_path):
    from app.brand import load_brand
    path = tmp_path / "brand.yml"
    path.write_text(
        """brand_status: DECIDED
name_fa: "راسته؟"
tagline_fa: "خبر و راستی‌آزمایی"
telegram_handle: "RastehNews"
""",
        encoding="utf-8",
    )
    brand = load_brand(str(path))
    assert brand.decided and brand.name_fa == "راسته؟"
    rendered = build_public_text("PROVISIONAL", "گزارش تازه‌ای درباره وضعیت خاورمیانه منتشر شده است.", brand, source_names="الجزیره")
    assert "نام نهایی هنوز انتخاب نشده است" not in rendered
    assert "— راسته؟ | خبر و راستی‌آزمایی" in rendered


def test_cached_preview_job_blocked_at_final_send_gate():
    from app.publishing.telegram_bot import publisher_language_gate
    bad = "🔴 **گزارش تازه‌ای درباره تحولات منطقه منتشر شده است.**\n\n— اخ‌بات | پیش‌نمایش سکوی خبری — نام نهایی هنوز انتخاب نشده است"
    assert not publisher_language_gate(bad)
    assert publisher_language_gate("🔴 **گزارش تازه‌ای درباره تحولات منطقه منتشر شده است.**\n\n— راسته؟ | خبر و راستی‌آزمایی")


def test_fallback_brand_cannot_be_published():
    from app.brand import load_brand
    from app.publishing.telegram_bot import brand_signature
    preview = load_brand("/nonexistent/rasteh_brand_preview.yml")
    try:
        brand_signature(preview)
    except ValueError:
        pass
    else:
        raise AssertionError("Preview brand must never reach the public channel")
