# 03-EDITORIAL-STYLE / سبک تحریریه

## قواعد خروجی عمومی (فارسی‌ONLY)
- تیتر معنادار (WHO+WHAT)؛ خبر تک‌واقعیتی = پست فشردهٔ تیتر-تنها مجاز؛ بدون فیلر، بدون تکرار تیتر/بدنه، بدون قطعهٔ شکسته، بدون متن خام فید، بدون نثر رباتیک راستی‌آزمایی، بدون هندل/URL خارجی.
- منبع شناخته‌شده دقیقاً یک‌بار: «منبع: نایا» / «منابع: نایا، یاشار».
- لید فقط اگر اطلاعات جدید می‌دهد؛ جزئیات فقط اگر مستند.

## آیکون‌ها
- چرخهٔ عمر (حداکثر ۱): 🟢 تأیید · 🔴 در حال راستی‌آزمایی · 🟠 متناقض · ⚠️ تأییدنیافتده/احتیاط · ❌ اصلاح/تکذیب. متن وضعیت برای خبر عادی نوشته نمی‌شود («✅ تأیید شد» ممنوع).
- ایموجی موضوعی (اختیاری، حداکثر ۱): ⚔️/🪖 نظامی · 🌐 اینترنت · 💵 ارز · 🪙 طلا · 🏛️ رسمی · 🌍 بین‌الملل · 📡 مخابرات · 📶 آماری. ایموجی منبع کپی نمی‌شود؛ ایموجی نباید واقعیتِ اثبات‌نشده را القا کند.

## قالب تلگرام
```
{آیکون چرخه} {ایموجی موضوعی؟} <b>تیتر فارسی</b>

{لید — فقط اگر تازه است}

منبع: {نام}

— راسته؟ | خبر و راستی‌آزمایی
🆔 @RastehNews
```
- HTML امن (`<b>`، escape کامل)؛ هرگز `**` خام؛ پانویس دقیقاً یک‌بار؛ فرمت رسانه: sendPhoto/sendVideo با همین کپشن (کپشن هم از GATE-08 می‌گذرد).
- تأییدِ provisional → ویرایش همان پیام، تبدیل 🔴→🟢، بدون پست دوم (INV-012/013).
- خطای قالب ۲۰۲۶-۱۰-۰۹: بارگذاری فایل واقعی `config/brand.yml` در کانتینر الزامی است؛ عبارت پیش‌نمایش/برند نامعلوم هرگز نباید به کانال عمومی راه پیدا کند. اگر تیتر کوتاه‌شده با «…» و لید کامل از یک عبارت شروع شوند، یک نسخه کامل نگه داشته شود، نه دو تکرار. تبلیغ منبع نیز حذف می‌شود.

## English — Telegram publishing invariants
- Mount the owner's `config/brand.yml` into `/srv/config/brand.yml` for every deployment; reject unresolved preview-brand signatures before rendering public Telegram content.
- Collapse a truncated headline duplicated by a longer lead without dropping factual words. Do not republish posts to fix format; edit the existing Telegram message ID and retain an original-content backup.
- Never touch other server projects while repairing this channel.
