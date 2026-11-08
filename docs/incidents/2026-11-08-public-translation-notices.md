# Public translation notices / اعلان عمومی خطای ترجمه

## Follow-up readability regression / تکمیل کنترل متن ناقص

Inspection of a completed SEND job found a mixed-script entity (`کrg`) and a lead cut off at a single letter. Its publication was actually **SKIPPED / QUALITY_MATERIALITY_FLOOR**, with no remote ID; a completed outbox job is not proof of a public send. Add independent rejection of mixed Persian/Latin words, dangling connector/single-letter endings and ellipses in any content paragraph. Translation candidates/cache, publisher boundaries and QA use the same check. Proper separated acronyms such as KRG/PUK remain allowed.

در بررسی یک کار پایان‌یافته، نام مخلوط و لید قطع‌شده پیدا شد؛ اما دفتر انتشار نشان داد همان مورد به‌دلیل ارزش خبری پایین رد شده و شناسهٔ تلگرام ندارد. پایان کارِ صف به معنی ارسال عمومی نیست. اکنون این عیب مستقل از ارزش خبری کنترل می‌شود: واژهٔ مخلوط فارسی/لاتین، پایان بریده با حرف منفرد یا حرف ربط و سه‌نقطهٔ ناقص در هر بند رد می‌شود؛ مخفف‌های جدا و صحیح مجازند. انتشار برای اعمال این اصلاح موقتاً متوقف و پس از بررسی نسخهٔ جدید به وضعیت قبلی بازگردانده می‌شود.

Long original-media captions now fall back to one complete text post; the publisher no longer slices the news at the caption boundary. Oversized text is blocked, and an existing photo is not edited with a sliced caption. Permanent `BLOCKED_*` results mark the attempted publication SKIPPED and complete the outbox job without failure retries; existing SENT target/history stays intact. Focused publisher/QA/media regressions: 53 PASS.

کپشن بلند اکنون به یک پیام متنیِ کامل تبدیل می‌شود؛ خبر در مرز طول مجاز بریده نمی‌شود. متن بیش‌ازحد بلند متوقف می‌شود و عکس قبلی با کپشن نصفه ویرایش نمی‌شود. خطای دائمی با وضعیت SKIPPED ثبت می‌شود و بیهوده تکرار نخواهد شد؛ سابقهٔ ارسال واقعی و شناسهٔ قبلی حفظ می‌شود. ۵۳ آزمون مرتبط موفق بود.

## Cause / علت

The live post-publication QA watcher used a separate old image. If a translation repair was unavailable or rejected, it queued a `publish_edit` containing an operational review notice. The notice was Persian and long enough to pass the final body/language checks. Successful QA repairs also used that old image's renderer, which predated the translated-lead fix. A read-only ledger audit found 177 historical completed jobs containing translation-related text; this is not a count of currently broken public messages.

ناظر مستقلِ نسخهٔ قدیمی در صورت شکست اصلاح ترجمه، اعلان بازبینی را در صف ویرایش عمومی قرار می‌داد. دروازهٔ نهایی این متن فارسی را محتوای خبری حساب می‌کرد. همان ایمیج قدیمی، اصلاح جدیدِ نمایش لید را هم نداشت. در سابقهٔ کارها ۱۷۷ مورد متن مرتبط با ترجمه پیدا شد؛ این عدد تعداد پیام‌های خرابِ فعلی کانال نیست.

## Changes / اصلاحات

- Failed QA repair records an internal `HOLD_TRANSLATION_QUALITY`, without queuing a public notice or making a new publication row.
- Operational notices/refusals are rejected in fresh/cached translation, final queue execution (SEND, EDIT and legacy handler), and all publisher API boundaries, including photos/videos.
- Broadcast-only program announcements without reporting are rejected. Real reporting and attributed quotes using words such as “cannot” remain allowed.
- Duplicate executions keep prior SENT ledger rows. QA discards results when the story advanced during the provider await, and conditionally updates by original version/timestamp.
- Short country aliases US/UK/UAE have letter boundaries; Russia/Ukraine no longer spuriously imply missing US/UK entities. Arabic newsroom-token leakage checks include the reproduced “عشرات” case.
- The previously isolated watcher source and tests are now tracked with the app, so both services can run the same release and renderer.

شکست اصلاح فقط در وضعیت داخلی ثبت می‌شود؛ اعلان خطا به کانال نمی‌رود. کش، صف قدیمی و همهٔ مسیرهای متن/عکس/ویرایش نیز کنترل می‌شوند. اعلان برنامهٔ رادیویی بدون متن خبر مسدود است، اما خبر واقعی و نقل‌قول معتبر با واژه‌های مشابه حذف نمی‌شود. سوابق واقعی ارسال حفظ می‌شوند و نتیجهٔ قدیمی ناظر نمی‌تواند نسخهٔ جدید خبر را بازنویسی کند. خطای تشخیص US/UK در Russia/Ukraine و یک نمونه نشت واژهٔ عربی نیز اصلاح شدند. کد ناظر اکنون کنار اپ ثبت شده تا هر دو سرویس نسخهٔ یکسان داشته باشند.

## Verification / آزمون

Before the fix, the exact production review notice passed both final checks and all four Telegram API methods; regression tests failed as expected. Failed-repair QA created an edit job. A concurrency reproduction advanced the story from version 1 to 5 during translation; old QA reset it to version 2 and queued an obsolete edit. These cases now pass, along with the real-news false-positive controls.

پیش از اصلاح، اعلان واقعیِ محیط زنده از هر دو دروازه و هر چهار روش انتشار تلگرام عبور می‌کرد. شکست اصلاح ناظر نیز کار ویرایش می‌ساخت. در آزمون هم‌زمانی، نسخهٔ جدید ۵ به نسخهٔ قدیمی ۲ بازمی‌گشت. آزمون‌های این موارد و کنترل خبرهای سالم اکنون موفق‌اند.

## Deployment / استقرار

At 2026-11-08 14:14 UTC both news services moved to `akhbot-app:quality-065843d`, revision `065843d889878d3494da1e22ad424627d62865d8`. The app was healthy, QA ran repeated passes, restart counts were zero, and the queue/failures-since-rollout were zero at the checkpoint. Three important module hashes matched between both containers. Runtime smoke used MockTransport and a temporary migrated database: four invalid-copy API paths blocked, valid copy allowed, and failed QA repair produced zero public jobs. It did not post a synthetic channel message. GitHub PR #12 CI passed; the backup passed SQLite quick_check and gzip verification, and old containers are retained for rollback.

در ۸ نوامبر ۲۰۲۶ ساعت ۱۴:۱۴ UTC هر دو سرویس خبر روی نسخهٔ یکسان بالا آمدند. سرویس خبر سالم بود، ناظر چند دور اجرا شد، شمار ریستارت‌ها صفر و صف معوق/کار ناموفق پس از استقرار در نقطهٔ کنترل صفر بود. هش ماژول‌های اصلی در دو کانتینر یکسان شد. آزمون داخل نسخهٔ زنده با انتقال‌دهندهٔ شبکهٔ شبیه‌سازی‌شده و پایگاه موقت انجام شد و هیچ پیام آزمایشی عمومی نفرستاد. CI شمارهٔ ۱۲ سبز است؛ پشتیبان تازه بررسی شد و کانتینرهای قبلی برای بازگشت حفظ شدند.

The complete isolated Linux run passed **533 tests** (24 existing deprecation warnings); 26 focused regressions passed locally. Latest-SENT payload reconstruction identified 13 historical suspect messages (8 review notices, 5 broadcast-only announcements); direct current Telegram contents were not inspected. No historical public message has been blindly deleted or replaced with an unvalidated draft. The correction does not claim automatic semantic understanding of every possible news item. Existing evidence, attribution, verification and language gates remain in force.

مجموعهٔ کامل Linux با ۵۳۳ آزمون موفق و ۲۴ هشدار منسوخ‌شدنِ قبلی اجرا شد؛ ۲۶ آزمون متمرکز نیز موفق بود. بازسازی آخرین ارسال‌ها از دفتر انتشار، ۱۳ پیام تاریخی مشکوک نشان داد: ۸ اعلان بازبینی و ۵ اعلان برنامه؛ محتوای فعلی تلگرام مستقیماً کنترل نشده است. هیچ پیام تاریخی به‌صورت کور حذف یا با پیش‌نویس تأییدنشده جایگزین نشده است. این اصلاح ادعای فهم معنایی کامل همهٔ خبرها را ندارد؛ کنترل‌های شواهد، انتساب، راستی‌آزمایی و زبان برقرارند.
