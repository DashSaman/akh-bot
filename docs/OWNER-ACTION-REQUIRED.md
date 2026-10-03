# OWNER ACTION REQUIRED — نهایی

تنها کارهایی که بدون تعامل انسانی مالک ممکن نیست. هر مورد قالب مشخص دارد؛
پس از انجام هر اقدام، هیچ تغییری در کد لازم نیست — فقط `.env` / تنظیمات و راه‌اندازی مجدد.

---

[BLOCKER]
Service: Telegram (Telethon)
Purpose: جمع‌آوری native با سرعت ثانیه‌ای + رسانه اصلی (بایت‌های اصلی عکس/ویدیو)
Exact page: https://my.telegram.org → API development tools
Exact action: ساخت API-ID/HASH؛ سپس در اولین اجرای listener با شماره‌ی حساب ربات، وارد کردن کد پیامکی (و رمز ۲FA در صورت فعال بودن) — یک‌بار
Expected result: فایل session برای TELEGRAM_INGEST_SESSION
What becomes enabled: INGEST-003 native (<5s)، MEDIA-003 بایت اصلی؛ تا آن زمان WEB_FALLBACK فعال و کامل است
Can project otherwise operate: YES

---

[BLOCKER]
Service: Google Gemini (پیشنهاد اول — سخاوتمندترین سطح رایگان)
Purpose: ترجمه عربی/انگلیسی/عبری → فارسی + راستی‌آزمایی محتوای AI (LANG-003/AI-002)
Exact page: https://aistudio.google.com/apikey
Exact action: ورود با Gmail مالک → Get API key → کپی کلید
Expected result: یک کلید AIza…
What becomes enabled: GEMINI_API_KEY=<key> در /opt/akhbot/.env سپس `bash scripts/deploy.sh` — ترجمه خودکار فعال می‌شود (بدون هیچ تغییر کد)
Can project otherwise operate: YES (عربی/خارجی HELD می‌ماند — هرگز خام منتشر نمی‌شود)
جایگزین‌های مجاز رایگان: Groq (console.groq.com/keys) یا OpenRouter (openrouter.ai/keys، مدل‌های free)

---

[BLOCKER]
Service: Meta (Instagram / Threads / Facebook)
Purpose: انتشار چندپلتفرمی (PLATFORM-002)
Exact page: https://developers.facebook.com/apps → Create App (Business type)
Exact action: افزودن محصولات Instagram Graph / Threads API، اتصاک اکانت، تولید User Token طولانی‌عمر — نیازمند لاگین انسانی مالک
Expected result: META_* توکن‌ها در .env
What becomes enabled: adapters مربوطه از AUTH_REQUIRED به LIVE
Can project otherwise operate: YES (تلگرام/وب کانال اصلی‌اند)

---

[BLOCKER]
Service: X (توییتر) API
Purpose: انتشار در X (نه جمع‌آوری)
Exact page: https://developer.x.com → Basic/Free tier
Exact action: ثبت اپ و تأیید حساب توسعه‌دهنده — نیازمند تأیید انسانی؛ سطح رایگان فقط write است
Expected result: X_BEARER_TOKEN
What becomes enabled: پلتفرم X برای انتشار
Can project otherwise operate: YES — بدون این، X برای انتشار BLOCKED_EXTERNAL باقی می‌ماند (سیاست هزینه: سطح پولی هرگز خریداری نشد)

---

[BLOCKER]
Service: دامنه عمومی وب‌سایت
Purpose: انتقال سایت از PREVIEW به LIVE عمومی + SEO/GSC
Exact page: DNS سرویس‌دهنده دامنه مالک
Exact action: رکورد A/AAAA به 91.107.240.235 (یا CNAME) + اطلاع به پشتیبانی برای فعال‌سازی vhost — سپس PUBLIC_BASE_URL در .env
Expected result: سایت خبری عمومی روی دامنه مالک
What becomes enabled: WEB-001/SEO کامل + sitemap در Google
Can project otherwise operate: YES (PREVIEW روی /latest فعال است)

---

[BLOCKER]
Service: Google Search Console
Purpose: پایش سئو (بعد از دامنه)
Exact page: https://search.google.com/search-console
Exact action: افزودن Property دامنه + تأیید مالکیت (DNS TXT) — تعامل انسانی
Expected result: پنل سئو مالک
What becomes enabled: ایندکس‌گذاری/پایش
Can project otherwise operate: YES

---

## خلاصه
| # | سرویس | فعال می‌شود | بدون آن |
|---|---|---|---|
| 1 | Telethon login | realtime + رسانه اصلی | WEB_FALLBACK (فعال) |
| 2 | Gemini/Groq/OpenRouter key | ترجمه زنده | خارجی HELD (بدون نشت) |
| 3 | Meta OAuth | IG/Threads/FB | تلگرام+وب |
| 4 | X API | انتشار X | BLOCKED (سیاست هزینه) |
| 5 | دامنه | وب عمومی | PREVIEW |
| 6 | GSC | پایش سئو | — |
