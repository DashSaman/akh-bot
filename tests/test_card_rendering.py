"""Visual regression guard for the branded Rasteh card v2 (MEDIA-REGRESSION).

The 10-fixture human visual gate (RTL shaping, no tofu, no cut-off, no
Markdown leakage) passed on 2026-10-03; these tests lock the machine-
checkable invariants so a regression (blank/black card, white bars,
wrong aspect, unstripped Markdown) fails CI before deploy.
"""
from __future__ import annotations

import statistics
from pathlib import Path

import pytest

from app.publishing import cards
from app.publishing.cards import _H, _W, _clean, render_card_v2

FIXTURES = [
    ("حمله پهپادی به تأسیسات نظامی در منطقه مرزی", "VERIFIED"),
    ("**تأییدنشده**: گزارش‌هایی از انفجار در بندر", "PROVISIONAL"),
    ("گزارش‌های متعارض درباره وضعیت مذاکرات میان طرفین", "CONFLICTING"),
    ("عنوان خبری بسیار طولانی " * 12, "PROVISIONAL"),  # wraps, never overflows
]


def _open(path: str):
    from PIL import Image
    return Image.open(path).convert("RGB")


def _lum(px) -> float:
    r, g, b = px
    return 0.299 * r + 0.587 * g + 0.114 * b


@pytest.mark.parametrize("headline,lifecycle", FIXTURES)
def test_card_size_1200x675(tmp_path, headline, lifecycle):
    out = str(tmp_path / "card.png")
    assert render_card_v2(headline, lifecycle=lifecycle, out_path=out) == out
    assert _open(out).size == (_W, _H)


@pytest.mark.parametrize("headline,lifecycle", FIXTURES)
def test_card_has_textured_content_not_blank(tmp_path, headline, lifecycle):
    out = str(tmp_path / "card.png")
    render_card_v2(headline, lifecycle=lifecycle, out_path=out)
    gray = _open(out).convert("L")
    assert sum(1 for c in gray.histogram() if c) > 40
    px = list(gray.getdata())
    assert statistics.pstdev(px[::37]) > 8


def test_card_brand_bar_and_dark_canvas(tmp_path):
    out = str(tmp_path / "card.png")
    render_card_v2("یک عنوان خبری نمونه", lifecycle="PROVISIONAL", out_path=out)
    img = _open(out)
    for x in (10, 600, 1190):
        assert img.getpixel((x, 4)) == cards._BRAND_GREEN
    # left margin stays dark navy — no meaningless white bar regression
    for y in (200, 340, 500):
        assert _lum(img.getpixel((30, y))) < 80


def test_card_markdown_never_rendered(tmp_path):
    out = str(tmp_path / "card.png")
    render_card_v2("**عنوان** با __نشانه__ و `کد`", lifecycle="VERIFIED",
                   out_path=out)
    assert Path(out).stat().st_size > 10_000  # real content, not a stub


def test_clean_strips_markdown_artifacts():
    assert _clean("**تأییدنشده**: حمله") == "تأییدنشده: حمله"
    assert "**" not in _clean("تست __بولد__ و `کد` و #سرتیتر")
    assert "\n" not in _clean("خط اول\nخط دوم")


def test_vazirmatn_fonts_shipped():
    base = Path(cards.__file__).parent / ".." / "assets" / "fonts"
    for weight in ("Bold", "Medium", "Regular"):
        assert (base / f"Vazirmatn-{weight}.ttf").is_file(), weight
