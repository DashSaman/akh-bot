"""Regression: public news must never end mid-claim or expose orphan source CTAs."""
from app.publishing.telegram_bot import build_public_text, public_body_is_substantive
from app.verification.gates import fit_headline


class Brand:
    name_fa = "راسته؟"
    tagline_fa = "خبر و راستی‌آزمایی"
    telegram_handle = "RastehNews"


IRANWIRE_TRUNCATED = (
    "وزارت خارجه جمهوری اسلامی، سفیر بریتانیا در تهران را در پی اتهام مقام‌های "
    "بریتانیایی درباره نقش ایران در طرح حمله به پایگاه هوایی فرفورد…"
)
IRANWIRE_FULL = (
    "وزارت خارجه جمهوری اسلامی، سفیر بریتانیا در تهران را در پی اتهام مقام‌های "
    "بریتانیایی درباره نقش ایران در طرح حمله به پایگاه هوایی فرفورد احضار کرد و "
    "هشدار داد در صورت ارائه نشدن مدارک، در روابط دوجانبه تجدیدنظر خواهد کرد."
)
TRUMP_SOURCE = (
    "دونالد ترامپ، رییس‌جمهوری آمریکا، گفت واشنگتن به‌زودی درباره گام بعدی خود "
    "در قبال جمهوری اسلامی تصمیم خواهد گرفت. او همچنین حوثی‌های یمن را به حمله "
    "به عربستان سعودی به دستور تهران متهم کرد و گفت ممکن است از رییس‌جمهوری "
    "ترکیه برای مقابله با این گروه کمک بخواهد."
)


def test_fit_headline_prefers_first_complete_sentence_not_ellipsis():
    h = fit_headline(TRUMP_SOURCE)
    assert h.endswith("تصمیم خواهد گرفت.")
    assert "حوثی" not in h
    assert not h.endswith("…")


def test_fit_headline_keeps_long_complete_single_sentence():
    h = fit_headline(IRANWIRE_FULL)
    assert h == IRANWIRE_FULL
    assert not h.endswith("…")


def test_renderer_repairs_real_iranwire_half_post_and_strips_cta():
    body = (
        IRANWIRE_TRUNCATED + "\n\n" + IRANWIRE_FULL +
        "\nبیشتر بخوانید: https://iranwire.com/fa/news-1/158844\n@Farsi_Iranwire"
    )
    out = build_public_text(
        "PROVISIONAL", body, Brand(), source_names="IranWire Telegram"
    )
    assert IRANWIRE_FULL in out
    assert IRANWIRE_TRUNCATED not in out
    assert "بیشتر بخوانید" not in out
    assert "iranwire.com" not in out
    assert "@Farsi_Iranwire" not in out
    assert "منبع: IranWire Telegram" in out
    assert public_body_is_substantive(out)


def test_renderer_keeps_new_suffix_instead_of_dropping_longer_detail():
    headline = (
        "نچیروان بارزانی، رییس اقلیم کردستان عراق، گفت مرزهای اقلیم با ایران "
        "بسته و نیروهای نظامی در امتداد آن مستقر شدند."
    )
    extra = "او گفت گروه‌های مخالف کرد ایرانی مستقر در اقلیم نیز از حمله به جمهوری اسلامی منع شدند."
    body = headline + "\n\n" + headline + " " + extra + "\nبیشتر بخوانید: https://example.test/x"
    out = build_public_text("PROVISIONAL", body, Brand(), source_names="IranWire Telegram")
    assert out.count(headline) == 1
    assert extra in out
    assert "بیشتر بخوانید" not in out


def test_final_send_body_gate_rejects_known_half_headline():
    public = (
        "🔴 **" + IRANWIRE_TRUNCATED + "**\n\n"
        "منبع: IranWire Telegram\n\n"
        "— راسته؟ | خبر و راستی‌آزمایی\n🆔 @RastehNews"
    )
    assert not public_body_is_substantive(public)


def test_orphan_read_more_is_never_substantive_content():
    public = (
        "🔴 **بیشتر بخوانید:**\n\nمنبع: IranWire Telegram\n\n"
        "— راسته؟ | خبر و راستی‌آزمایی\n🆔 @RastehNews"
    )
    assert not public_body_is_substantive(public)
