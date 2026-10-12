"""Regression: Rasteh #1581 lost 'کانال ۱۲ اسرائیل' from a military claim."""
from app.newsroom.claim_model import extract_structured
from app.newsroom.story_evolution import select_headline


def test_source_attribution_must_survive_claim_to_public_headline():
    source = (
        "کانال ۱۲ اسرائیل: پنتاگون به فرماندهی مرکزی آمریکا(سنتکام) دستور داده است "
        "آماده‌سازی‌ها برای احتمال ازسرگیری عملیات‌های گسترده نظامی علیه ایران را تکمیل کند."
    )
    claim = extract_structured(source, source_item_id=0)
    assert claim.actor == "کانال ۱۲ اسرائیل"
    public = select_headline([{"id": 1, "text": claim.text, "actor": claim.actor,
                               "state": "UNVERIFIED"}])
    assert "کانال ۱۲ اسرائیل" in public
    assert "پنتاگون" in public
