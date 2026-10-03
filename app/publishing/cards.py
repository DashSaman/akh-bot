"""Branded Rasteh fallback card v2 — proper Persian RTL rendering.

Replaces the broken Pillow card (default-font tofu / white bars, owner
screenshot). Uses Vazirmatn (OFL) + arabic_reshaper + python-bidi:

  - 1200×675 (16:9, Telegram/social correct)
  - dark navy gradient, brand green bar, typographic «راسته؟» mark
  - lifecycle chip drawn as shapes + Persian text (NO emoji → no tofu)
  - headline reshaped, bidi-ordered, width-wrapped, auto-shrink (≤4 lines)
  - strips Markdown artifacts before drawing

Gated behind settings.media_fallback_cards_enabled — stays OFF until the
10-fixture visual regression passes (MEDIA-REGRESSION).
"""
from __future__ import annotations

import os
import re

_W, _H = 1200, 675
_BG_TOP = (13, 21, 32)
_BG_BOTTOM = (20, 34, 48)
_BRAND_GREEN = (63, 185, 80)
_TEXT = (230, 237, 243)
_TEXT_DIM = (154, 167, 179)
_HANDLE_BLUE = (88, 166, 255)
_CHIP_COLORS = {  # lifecycle → (dot, label)
    "PROVISIONAL": ((248, 81, 73), "تأییدنشده"),
    "CONFLICTING": ((255, 154, 60), "گزارش‌های متعارض"),
    "VERIFIED": ((63, 185, 80), "تأییدشده"),
}
_MD_RE = re.compile(r"(\*\*|__|`+|\*|_|#+)")


def _shape(text: str) -> str:
    """Persian shaping + bidi reordering for correct RTL display."""
    import arabic_reshaper
    from bidi.algorithm import get_display
    return get_display(arabic_reshaper.reshape(text or ""))


def _font(size: int, weight: str = "Bold"):
    from PIL import ImageFont
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "assets", "fonts", f"Vazirmatn-{weight}.ttf")
    return ImageFont.truetype(os.path.abspath(path), size)


def _clean(text: str) -> str:
    return _MD_RE.sub("", (text or "").replace("\n", " ")).strip()


def _gradient(img) -> None:
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    for y in range(_H):
        t = y / _H
        color = tuple(int(a + (b - a) * t) for a, b in zip(_BG_TOP, _BG_BOTTOM))
        d.line([(0, y), (_W, y)], fill=color)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render_card_v2(headline: str, lifecycle: str = "PROVISIONAL",
                   out_path: str = "") -> str:
    """Render one branded card; returns path. Raises on any font/shape issue."""
    from PIL import Image, ImageDraw

    headline = _clean(headline)
    if not headline:
        raise ValueError("empty headline")
    img = Image.new("RGB", (_W, _H), _BG_TOP)
    _gradient(img)
    d = ImageDraw.Draw(img)

    # brand bar + mark
    d.rectangle([0, 0, _W, 10], fill=_BRAND_GREEN)
    mark_font = _font(44)
    d.rounded_rectangle([_W - 218, 48, _W - 52, 116], radius=18,
                        fill=_BRAND_GREEN)
    d.text((_W - 135, 82), _shape("راسته؟"), font=mark_font, fill=(13, 21, 32),
           anchor="mm")

    # lifecycle chip (dot + Persian label, top-left)
    dot, label = _CHIP_COLORS.get(lifecycle, _CHIP_COLORS["PROVISIONAL"])
    chip_font = _font(30, "Medium")
    label_sh = _shape(label)
    tw = d.textlength(label_sh, font=chip_font)
    d.ellipse([64, 66, 92, 94], fill=dot)
    d.text((106, 80), label_sh, font=chip_font, fill=_TEXT_DIM, anchor="lm")

    # headline — auto-shrink to ≤4 lines, right-aligned RTL
    shaped = _shape(headline)
    max_w = _W - 128
    for size in (64, 56, 48, 42):
        f = _font(size)
        lines = _wrap(d, shaped, f, max_w)
        if len(lines) <= 4:
            break
    y = 250 if len(lines) <= 3 else 210
    for line in lines[:4]:
        d.text((_W - 64, y), line, font=f, fill=_TEXT, anchor="ra")
        y += int(size * 1.42)

    # footer
    foot_font = _font(30, "Medium")
    d.text((_W - 64, _H - 56), _shape("خبر و راستی‌آزمایی"),
           font=foot_font, fill=_TEXT_DIM, anchor="rm")
    d.text((64, _H - 56), "@RastehNews", font=_font(30, "Medium"),
           fill=_HANDLE_BLUE, anchor="lm")

    out = out_path or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "data",
        "media", f"card-v2-{int(__import__('time').time())}.png")
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out, "PNG")
    return out
