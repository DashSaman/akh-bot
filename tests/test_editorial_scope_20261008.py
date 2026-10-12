"""Regression: unrelated global headlines must not fill Iran-first channel."""
from app.newsroom.iran_policy import in_editorial_scope
from app.newsroom.quality_gates import publication_quality_gate


def test_iran_and_neighboring_conflicts_allowed():
    assert in_editorial_scope("تحریم‌های جدید علیه ایران")
    assert in_editorial_scope("حمله موشکی به پایگاه نظامی در عراق")
    assert in_editorial_scope("افزایش صادرات نفت عربستان")
    assert in_editorial_scope("گفت‌وگوی تهران و واشنگتن درباره برنامه هسته‌ای")


def test_global_filler_and_regional_trivia_blocked():
    assert not in_editorial_scope("نتیجه مسابقه فوتبال در برزیل")
    assert not in_editorial_scope("مراسم افتتاح یک پارک در ترکیه")
    assert not in_editorial_scope("انتخابات شهرداری در کانادا")
    assert publication_quality_gate(None, "انتخابات شهرداری در کانادا", "", 95) == "OUT_OF_EDITORIAL_SCOPE"
