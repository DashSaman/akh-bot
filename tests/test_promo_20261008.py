"""Real Telegram regression: casino reward advertisement in a news feed."""
from app.newsroom.quality_gates import promotional_content, publication_quality_gate


def test_casino_promo_from_rasteh_screenshot_blocked():
    headline = "بازار آپشنه بری بت"
    body = "با فعالیت در بخش های کازینو و پیش بینی ورزشی امتیاز کسب کنید. بعد از جمع آوری امتیازات، آن ها را در گنجینه به جایزه تبدیل کنید. کانال تلگرام:"
    assert promotional_content(headline, body)
    assert publication_quality_gate(None, headline, body, 95) == "HOLD_PROMOTIONAL_CONTENT"


def test_reporting_on_gambling_not_advertising():
    assert not promotional_content("پلیس ایران شبکه شرط بندی را تعطیل کرد", "متهمان بازداشت شدند")
    assert not promotional_content("قیمت نفت در عراق افزایش یافت", "گزارش اقتصادی")
