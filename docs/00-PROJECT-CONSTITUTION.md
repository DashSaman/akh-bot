# 00-PROJECT-CONSTITUTION / قانون اساسی پروژه

# فارسی
این سند بالاترین مرجع الزامات مالک برای akh-bot/راسته‌نیوز است. **گزارش‌های پیاده‌سازی آن را باطل نمی‌کنند.** جدیدترین تصمیم مالک، الزام قدیمی‌تر متناقض را نسخ می‌کند.

## الزامات هستهٔ ساختاری (پیوند با ماتریس)
CORE-001 موجودیت‌های قانونی (Source, RawItem, Claim, Event, Story, StoryVersion, PublicationJob/Ledger) · CORE-004 مدل StoryVersion · CORE-005 مدل outbox/ledger انتشار · CORE-006 موجودیت‌های پشتیبان (MediaAsset/EvidenceLink/VerificationRun/PlatformAccount)

## شناسه‌های الزام (دسته‌ها)
`CORE` هسته · `SRC` منابع · `INGEST` گردآوری · `CLAIM` ادعا · `EVENT` رویداد · `VERIFY` راستی‌آزمایی · `LANG` زبان · `EDIT` تحریریه · `MEDIA` رسانه · `PUB` انتشار · `PLATFORM` پلتفرم · `ADMIN` پنل · `AI` هوش مصنوعی · `AUT` خودمختاری · `WATCH` پایش · `SEC` امنیت · `PORT` قابلیت‌حمل · `WEB` وب‌سایت · `SEO` سئو · `GROWTH` رشد

## ناورداهای غیرقابل‌نقض (INV)

| ID | ناوردای |
|---|---|
| INV-001 | SourceItem ≠ Claim ≠ Event ≠ Story ≠ Publication (پنج موجودیت مجزا) |
| INV-002 | هیچ RawItem مستقیماً به ناشر عمومی نمی‌رود |
| INV-003 | همهٔ خروجی عمومی از یک Story/StoryVersion یکتا می‌آید |
| INV-004 | همهٔ ناشران از دروازهٔ نهایی FAIL-CLOSED عبور می‌کنند |
| INV-005 | SOURCE_ALLOWLIST_MODE همیشه در کنترل مالک است |
| INV-006 | اولویت منبع فقط سرعت پردازش است، هرگز اعتبار واقعی |
| INV-007 | زبان عمومی تحریریه = فارسی |
| INV-008 | محتوای خام خارجی هرگز فال‌بک عمومی نیست |
| INV-009 | یک مصاحبه/بیانیه/حادثه/رویداد در حال تحول ← عمدتاً یک Story در حال تکامل |
| INV-010 | چند پیام منبع، خودبه‌خود چند Story عمومی نیست |
| INV-011 | ادعا/تیتر ناقص منتشر نمی‌شود (ممنوع: «ترامپ:»، «عاجل:»، «BREAKING:»، «ترامپ در مصاحبه با مجله تایم:») |
| INV-012 | ادعای جدیدِ رویدادِ عمومی‌شده ← به‌روزرسانی همان پیام عمومی |
| INV-013 | پست تأییدشدهٔ عادی هرگز متن «✅ تأیید شد» ندارد |
| INV-014 | تکرار معنایی تیتر/بدنه ممنوع |
| INV-015 | انتساب منبعِ شناخته‌شده دقیقاً یک‌بار |
| INV-016 | URL/هندل خارجی در متن عمومی عادی نمایش نمی‌یابد |
| INV-017 | هوش مصنوعی اختیاری است |
| INV-018 | شکست AI تحریریهٔ قطعی را کرش نمی‌کند |
| INV-019 | هیچ AI واقعیتِ بدون پشتوانه نمی‌سازد |
| INV-020 | رسانهٔ موقت تهدید دیسک مشترک نیست |
| INV-021 | Zed/Z.ai/مرورگر/SSH هرگز وابستگی زمان-اجرأ نیست |
| INV-022 | سرویس‌ها/پورت‌ها/تونل‌ها/کانتینرهای غیرمرتبط فقط-خواندنی‌اند مگر مجوز صریح مالک |
| INV-023 | گزارش عامل قبلی = مدرک پیاده‌سازی نیست |
| INV-024 | DONE = کد + تست + شاهد زمان-اجرأ (هرجا رفتار اجرایی مهم است) + همگام‌سازی مستندات |
| INV-025 | هر رگرسیون تولیدیِ مشاهده‌شده ← تست رگرسیون دائمی |

## جریان دادهٔ قانونی (تنها مسیر عمومی مجاز)
SOURCE → RAW ITEM → NORMALIZATION → LANGUAGE DETECTION → CLAIM EXTRACTION → ITEM DEDUP → EVENT MATCH/CREATE → CLAIM MERGE → VERIFICATION → CANONICAL STORY → STORY VERSION → PERSIAN TRANSLATION/EDITORIAL REWRITE → EDITORIAL QUALITY GATES → PUBLICATION POLICY → PLATFORM RENDERER → **FINAL FAIL-CLOSED GATE** → OUTBOX → PLATFORM PUBLISHER

## قاعدهٔ رویداد/ادعا (D)
یک منبع ممکن است یک رویداد واقعی را در چند پیام بشکند (۶ قطعه از یک مصاحبه ترامپ/تایم). مدل صحیح: ۶ RawItem → ۶ Claim → **۱ Event** → ۱ Story در حال تکامل → ۱ پیام تلگرام. الزامات: `EVENT_IDENTITY`، `EVENT_MATCHING`، `CLAIM_DEDUP`، `CLAIM_MERGE`، `SAME_STORY_UPDATE`

## سیاست رشتهٔ رویداد (E)
`EVENT_BURST_WINDOW_SECONDS` · `EVENT_CONTINUATION_WINDOW_MINUTES` · `SAME_EVENT_UPDATE_MODE` · `HIGH_PRIORITY_BREAKING_MODE` — فوریِ مهم: اولین ادعای کاملِ معنادار بی‌درنگ منتشر می‌شود؛ ادعاهای بعدی همان رویداد ادغام و همان پیام ویرایش می‌شود؛ غیرفوری: پنجرهٔ تجمیع کوتاه مجاز؛ هیچ‌گاه خبر فوری کامل به‌خاطر انتظار برای پیام‌های بعدی عقب نیفتد.

## گیت کامل بودن ادعا (F) — GATE-CLAIM-COMPLETE
ادعا بدون پاسخِ حداقلی به WHO+WHAT (و WHERE/WHEN/CONTEXT در صورت ارتباط) عمومی نمی‌شود. «ترامپ در مصاحبه با مجله تایم:» = FAIL (پیشوند گوینده metadata است، نه ادعا).

## قاعدهٔ مدرک (H)
DONE نیازمند: کد + تست + شاهد زمان-اجرأ + مستندات. وجود کلاس ≠ کافی؛ تست mock برای ادعای ریل‌تایم کافی نیست؛ «PASS» گفتنِ عامل مدرک نیست.

## سیاست منبع فعلی مالک (R)
SOURCE_ALLOWLIST_MODE=ON (اجرا در `due()`+execution-check؛ کلید نشانه در settings خالی است — ثبت صادقانه) · اولویت ۱: naya_foriraq · ۲: withyashar · بقیه OWNER_DISABLED از /admin/sources. اولویت فقط سرعت.

## مدیریت خصوصی (S)
VPS: 91.107.240.235 · ادمین: https://rasteh.softarg.ir (دو لایه: Basic+اپ) · بک‌اند 127.0.0.1:8307 (عمومی نیست). ادمین نهایتاً بدون SSH: منابع/پلتفرم‌ها/مدیا/AI/سلامت/ورودی دستی/تنظیمات.

## ایمنی میزبان (T)
هرگز تغییر/ری‌استارت/حذف کانتینرها، پورت‌ها، vhostهای آپاچی، xray، تونل‌ها، دیتابیس‌ها، شبکه‌های غیرمرتبط. تعارض گزارش می‌شود نه حل با دست‌زدن. پرون سراسری داکر و ری‌استارت داکمون ممنوع.

---

# English
This is the HIGHEST AUTHORITY for owner requirements of akh-bot/RastehNews. **Implementation reports do not override it.** Newest owner decision supersedes older conflicting requirements. Structure mirrors the Persian section above: requirement ID categories (CORE…GROWTH), the 25 non-negotiable invariants INV-001..025, the canonical data flow (the ONLY allowed public path), the Event/Claim rule (6 messages → 1 Event → 1 evolving Story → 1 message), burst policy config keys, GATE-CLAIM-COMPLETE (WHO+WHAT minimum; speaker prefix = metadata), evidence rule (DONE = code+test+runtime+docs), owner source policy (allowlist ON; naya=1, yashar=2; priority=speed only), private admin architecture, host-safety invariants.
