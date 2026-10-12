"""Real Arabic-to-Persian regression: published Rasteh #1595 on 2026-10-08."""
from app.newsroom.translator import consistency_issues


SOURCE = (
    "تسريبات أمريكية بشأن ضرب إيران بالتوازي مع مفاوضات الملف النووي. "
    "تتزايد التسريبات الأمريكية بشأن احتمال توجيه ضربة عسكرية لإيران "
    "قبل انتخابات الكونغرس المقررة في الثالث من نوفمبر."
)
BAD_PUBLIC = (
    "افشای آمریکاییها درباره حمله به ایران همزمان با مذاکرات هستهای. "
    "افشاگریهای آمریکاییها افزایش یافته است و گزینههای حمله به زیرساختها آماده می‌شود."
)
GOOD_PUBLIC = (
    "گزارش‌های افشاشده آمریکایی درباره احتمال حمله به ایران همزمان با مذاکرات هسته‌ای. "
    "انتشار این گزارش‌ها پیش از انتخابات کنگره در سوم نوامبر افزایش یافته است."
)


def test_1595_rejects_real_malformed_persian_forms():
    issues = consistency_issues(SOURCE, BAD_PUBLIC)
    for word in ("آمریکاییها", "هستهای", "افشاگریهای", "گزینههای", "زیرساختها"):
        assert f"PERSIAN_ORTHOGRAPHY:{word}" in issues


def test_1595_accepts_natural_persian_forms():
    assert not any(x.startswith("PERSIAN_ORTHOGRAPHY:")
                   for x in consistency_issues(SOURCE, GOOD_PUBLIC))


def test_1586_arabic_military_escalation_is_not_literal_persian_calque():
    source = "اتصالات واشنطن وطهران تتواصل وتصعيد عسكري يتسع في اليمن وغزة والضفة"
    bad = "گفت‌وگوی واشینگتن و تهران ادامه می‌یابد و تصاعد نظامی در یمن و غزه گسترش می‌یابد"
    good = "گفت‌وگوهای واشینگتن و تهران ادامه دارد و تنش‌های نظامی در یمن و غزه تشدید شده است"
    assert "PERSIAN_CALQUE:تصاعد_نظامی" in consistency_issues(source, bad)
    assert "PERSIAN_CALQUE:تصاعد_نظامی" not in consistency_issues(source, good)
