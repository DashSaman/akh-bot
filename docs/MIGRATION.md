# Migration & Portability / مهاجرت و قابلیت‌حمل (بilingual)

# فارسی

## انتقال به سرور دیگر — خلاصه ۸ مرحله
1. بکاپ اکسیژنار: `bash scripts/backup_db.sh` (SQLite آنلاین) — فایل در `akhbot_data:/data/backups/`
2. انتقال: فایل DB + `/opt/akhbot/.env` (رمزها — خارج از گیت) به سرور جدید
3. کلون ریپو در سرور جدید: `/opt/akhbot/app`
4. `.env` جدید با همان کلیدها (SESSION_SECRET جدید هم مجاز است)
5. استقرار: `bash scripts/deploy.sh` → والیوم `akhbot_data` ساخته می‌شود
6. بازگردانی: `bash scripts/restore_db.sh <backup.db>` (کانتینر متوقف، DB جایگزین، health)
7. راستی‌آزمایی تک‌فرمانی: `bash scripts/verify_instance.sh` (خروج غیرصفر = شکست بحرانی)
8. پایش چند چرخه: ضربان‌ها باید جلو بروند (`settings` جدول: `*_last_run`)

## چه چیزی منتقل می‌شود (اجباری)
رویدادها، داستان‌ها و نسخه‌ها، **دفتر انتشار** (chat_id + remote message ids + payload hash) → تضمین عدم پست تکراری پس از مهاجرت · ثبت‌نام منابع + **checkpointها** (watermark در `fetch_state`) · اولویت‌ها/breaking/اجازه‌های راستی‌آزمایی · برند (`config/brand.yml`)

## چه چیزی منتقل نمی‌شود
- **مدیا**: کش موقتی است؛ فقط hash/حقوق/شناسه‌های ریموت می‌مانند؛ در سرور جدید دوباره واجد شرایط fetch می‌شود
- **رمزها/کلیدها/session**: هرگز در بکاپ معمولی/گیت نیستند؛ `.env` دستی منتقل می‌شود
- **Telethon session**: محرمانه است — در صورت نیاز به realtime، فایل/رشته session را جداگانه و محافظت‌شده منتقل کنید؛ در غیاب آن سیستم با `WEB_FALLBACK` + وضعیت `TELETHON_AUTH_REQUIRED` بالا می‌آید (نه خطا)

## AI پیکربندی‌پذیر اما اختیاری
ترتیب ارائه‌دهنده/مدل/FREE_ONLY/ZERO_COST_MODE در env می‌ماند. کلید غایب → `DETERMINISTIC_MODE` (نه شکست).

## نصب تمیز (بدون DB قبلی)
کاتالوگ پایه از `config/source-seed.example.yml` **فقط وقتی جدول sources خالی است** بارگذاری می‌شود (`app/db/seed.py`). seed ≠ تأیید تحریریه — وضعیت اعتماد runtime جدا است. در اولین فعال‌سازی، هویت واقعی (شناسه پایدار/هندل فعلی/URL متعارف) کشف و ثبت می‌شود.

# English

## Moving to another VPS — 8 steps
Export (online SQLite backup) → transfer DB + `.env` (secrets, out of git) → clone repo → configure secrets → `deploy.sh` → `restore_db.sh` → **`verify_instance.sh`** (single command, non-zero exit on critical failure) → observe heartbeats advancing.

**Must survive:** events/stories/versions, the **publication ledger** (chat_id, remote message ids, payload hashes → no duplicate posts), source registry + **watermark checkpoints** (in `fetch_state`), priorities/breaking/verification flags, brand config.

**Never migrated:** media cache (hash+rights+remote IDs only; re-fetch on demand), secrets (manual `.env` transfer), Telethon session (secret; absent → `WEB_FALLBACK` + `TELETHON_AUTH_REQUIRED`, newsroom still runs).

**AI config** (provider order/models/FREE_ONLY/ZERO_COST_MODE) is env-based; missing keys → `DETERMINISTIC_MODE`, never failure.

**Clean install:** baseline catalog loads from `config/source-seed.example.yml` ONLY when the sources table is empty; seed ≠ editorial approval; remote identity is resolved/stored on first activation.
