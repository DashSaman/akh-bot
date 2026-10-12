"""Real Rasteh Telegram regressions observed on 2026-10-08."""
import asyncio
import json

from app.db.repo import LlmCacheRepo
from app.newsroom.translator import _cache_key, consistency_issues, translate_event


HEBREW_SOURCE_1571 = '🔴 בריטניה: "הקונסוליה לא נסגרת, אלא משנה את שמה. נמשיך להעניק שם שירות"'
BAD_1571 = {
    "headline": "بریتانیا: کنسولگری بریتانیا در ایران نام خود را تغییر می‌دهد اما فعالیت خود را ادامه می‌دهد.",
    "lead": "بریتانیا اعلام کرد که کنسولگری بریتانیا در ایران نام خود را تغییر می‌دهد.",
}
ARABIC_SOURCE_1562 = (
    "تتجه دولة الإمارات نحو محطة استثنائية في مسارها الاقتصادي بحلول عام 2027، "
    "وسط مؤشرات متصاعدة تؤكد اقتراب تسجيل قفزة نمو تاريخية مدفوعة برؤية تنموية "
    "شاملة وزخم قوي في مختلف القطاعات الإنتاجية والنقدية."
)


def test_1571_hebrew_consulate_source_must_not_gain_iran_location():
    assert "UNSUPPORTED_IRAN_LOCATION" in consistency_issues(
        HEBREW_SOURCE_1571, BAD_1571["headline"] + " " + BAD_1571["lead"]
    )
    assert "UNSUPPORTED_IRAN_LOCATION" not in consistency_issues(
        'הקונסוליה באיראן לא נסגרת', BAD_1571["headline"]
    )


def test_1562_arabic_momentum_must_not_be_persian_wound():
    assert "PERSIAN_CALQUE:زخم_قوی" in consistency_issues(
        ARABIC_SOURCE_1562,
        "امارات با زخم قوی در بخش‌های تولیدی و مالی به رشد اقتصادی نزدیک می‌شود"
    )
    assert "PERSIAN_CALQUE:زخم_قوی" not in consistency_issues(
        ARABIC_SOURCE_1562,
        "امارات با شتاب بالای رشد در بخش‌های تولیدی و مالی به پیش می‌رود"
    )


def test_1571_invalid_cached_translation_is_not_accepted(db):
    title = HEBREW_SOURCE_1571
    key = _cache_key("he", title, HEBREW_SOURCE_1571)
    LlmCacheRepo(db).put(key, json.dumps(BAD_1571, ensure_ascii=False),
                         "regression", "fa-rewrite-v10", 0, 0, 0)

    class NoResultRouter:
        available = True
        async def chat_json(self, **kwargs):
            return None

    result = asyncio.run(translate_event(
        NoResultRouter(), title, HEBREW_SOURCE_1571,
        db=db, source_language="he"
    ))
    assert result is None, "invalid cache must fail closed when provider unavailable"
