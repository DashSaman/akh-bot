# فارسی

# منابع

- فقط منابع `APPROVED` جمع‌آوری می‌شوند. `DISCOVERED` مورد اعتماد نیست؛ سیستم می‌تواند پیشنهاد بدهد اما فقط مدیر تأیید می‌کند.
- هر منبع: نام، پلتفرم (rss/telegram/x/website)، شناسه پایدار، زبان، کشور، دسته، نوع منبع (نهاد رسمی/رسانه/خبرنگار/ناظر محلی/...)، اولویت، فاصله نظرسنجی، سلامت.
- **حفاظت بازگشتی:** تأیید منبع `activated_at` را ثبت می‌کند؛ محتوای قدیمی‌تر فقط ذخیره می‌شود (activation_ok=0) و هرگز واجد شرایط انتشار خودکار نیست.
- **ETag/If-Modified-Since** برای RSS؛ پاسخ 304 = بدون تغییر، بدون هزینه.
- سلامت (health_score) سیگنال اعتماد است، نه حقیقت؛ با خطا افت می‌کند، با موفقیت بازمی‌گردد.

# English

# Sources

- Only `APPROVED` sources are ingested. `DISCOVERED` is never trusted until an admin
  approves; `BLOCKED` stops everything.
- Stored fields per source: name, platform, stable external id, language, country,
  category, source type (official institution / news org / journalist / local observer /
  telegram aggregator / ...), priority, polling interval, health.
- **Backfill protection:** approval stamps `activated_at`; older content is stored
  only (`activation_ok=0`) and never auto-publish eligible.
- RSS uses ETag/If-Modified-Since (304 = skip, zero cost).
- `health_score` is a reliability signal, not truth: decays on errors, recovers on success.

## MASTER-FINAL: رجیستری کامل مالک (XLSX) — ۱۱۰ اندپوینت / ۷۸ هویت
- منبع: `rasteh_external_sources_iran_2026.xlsx` مالک → تبدیل برنامه‌ای: `scripts/import_source_xlsx.py` → `import_full_registry()`
- هویت canonical = ستون Entity ID (authoritative): اندپوینت‌های یک سازمان/شخص هرگز خاستگاه مستقل را متورم نمی‌کنند (تست‌شده §24)
- نقش‌ها (§6): Independent newsroom / Official primary / Direct person / Mirror / OSINT data / Analysis — در `role_detail` + ستون‌های رفتاری
- سطح سرعت (§8): FAST 120s / MID 240s / SLOW 600s / EVENT 1800s + jitter داخلی scheduler
- فعال‌سازی صادقانه (§17): ACTIVE 58 (تلگرام web + RSS مستقیم + فید عمومی Google News برای نیوزروم‌های bot-protected — اندپوینت عمومی رسمی، بدون دور زدن هیچ paywall/robots) · BLOCKED_AUTH 27 (X/TruthSocial) · UNSUPPORTED 25 (اسناد رسمی/OSINT/افراد بدون فید عمومی)
- کشف فید: `scripts/discover_feeds.py` (فقط `<link rel=alternate>` عمومی) · فعال‌سازی مرحله‌ای: `scripts/activate_endpoints.py`
