# Native Persian routing / مسیر خبر فارسی — 2026-11-08

## فارسی

تشخیص زبان با چند حرف مشترک انجام می‌شد: «آ» می‌توانست متن عربی را فارسی کند
و خبر فارسی دارای نام لاتین به‌علت نسبت حروف لاتین وارد ترجمه می‌شد.
همچنین ناظر کیفیت، نسخهٔ فارسی اصلی را با زیرمجموعهٔ خارجی گزارش‌های همان
رویداد مقایسه می‌کرد؛ اختلاف واقعی گزارش‌ها می‌توانست ترجمهٔ بی‌مورد ایجاد کند.

اکنون نشانه‌های دستوری متن، بدون امضا و لینک، بررسی می‌شوند. فارسی روشن
با نام‌های لاتین به مدل ترجمه نمی‌رود؛ فقط «ي/ك» در نسخهٔ نمایشی به «ی/ک»
تبدیل می‌شوند. متن و ادعاهای اصلی حفظ می‌شوند. برچسب اشتباه fa برای عربی
در انتخاب مسیر مدل اصلاح می‌شود. متن مبهم همچنان تابع زبان منبع و کنترل
نهایی انتشار است. جملهٔ فارسی نمی‌تواند پاراگراف خارجی را از کنترل عبور دهد.

پیش‌نویس‌ها وضعیت translated را ثبت می‌کنند. ناظر ترجمه، نسخهٔ فارسی اصلی
را بازترجمه نمی‌کند؛ در رکوردهای قدیمی باید عنوان و تمام بدنه با یک گزارش
فارسی اصلی مطابقت داشته باشند. صرف وجود گزارش فارسی دیگر کافی نیست.
بازنویسی گروهی برچسب‌های قدیمی یا بازگرداندن خودکار صف اخبار قدیمی انجام نشد.

## English

Single-character language detection confused Arabic madda and Persian names.
The publication script-ratio check also routed Persian stories containing Latin
entities into translation. QA could retranslate a native Persian story against
a different foreign report attached to the same event.

Positive Persian syntax now guides routing independently of source metadata,
with footers/links excluded and each sentence checked. Clearly Persian reports
with Latin names stay native; only Arabic yeh/kaf display variants normalize.
Raw evidence and claims remain unchanged. Mislabeled Arabic receives the Arabic
model route. Ambiguous reports retain source-language and final publication gates.

V2 drafts persist translation provenance through creation and updates. Translation
QA skips native originals; legacy inference requires every published content part
to match one native report. An unrelated Persian report cannot exempt a translation.
No historical mass relabeling, public test post, or blind backlog retry is used.

## Verification

Regression tests reproduce source misclassification, Latin-name translation,
Arabic letter variants, Arabic evidence mislabeled fa, mixed foreign paragraphs,
and QA retranslation of a native original. Run `python -m pytest tests -q` in the
isolated Linux harness before production rollout. Deployment results are recorded
in the latest checkpoint in `docs/00-CURRENT-STATUS.md`.
