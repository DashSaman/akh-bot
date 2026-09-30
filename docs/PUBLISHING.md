# فارسی

# انتشار

## ناشر مستقل per پلتفرم
`TelegramBotPublisher` (فعال) + X/Instagram/Threads/Facebook (آماده‌سازی؛ پس از اعتبارنامه). خطای یک پلتفرم بقیه را متوقف نمی‌کند.

## دفتر انتشار (idempotency اجباری)
هر تلاش در `publications` ثبت می‌شود: `UNIQUE(story_id, platform, payload_hash)`.
قبل از هر ارسال، SENT بودن همان payload بررسی می‌شود → retry/restart هرگز پست تکراری نمی‌سازد. remote message id ذخیره می‌شود (برای edit/correction).

## محتوای متمایز per پلتفرم
تلگرام کامل‌تر + «هنوز تأیید نشده»؛ X کوتاه پرنرم‌افزار؛ وب کامل با شواهد/خط زمانی/منابع.

## محدودسازی نرخ
سقف پست در ساعت/روز (`MAX_POSTS_PER_HOUR/DAY`)؛ backoff نمایی برای خطا؛ jitter از طریق زمان‌بند.

## کلید توقف
`pause_all` و `pause_platform:*` — جمع‌آوری ادامه دارد، انتشار نه.

## اصلاحیه‌ها
ویرایش داستان نسخه جدید می‌سازد؛ اصلاح جدی در همه پلتفرم‌های منتشرکننده با edit اعمال و تاریخچه شفاف نگه داشته می‌شود.

# English

# Publishing

Independent per-platform publishers (Telegram active; X/Instagram/Threads/Facebook
prepared). One platform failing never stops the others.

**Idempotent ledger:** every attempt recorded in `publications` with
`UNIQUE(story_id, platform, payload_hash)`; SENT payloads are checked before any API
call — retries/restarts never duplicate posts. Remote message ids enable edits/corrections.

Platform-specific content (Telegram fuller + uncertainty block; X compact; web full
evidence/timeline/sources). Rate caps per hour/day; exponential backoff. Kill switches:
`pause_all`, `pause_platform:*` (collection continues). Corrections version stories and
propagate edits across platforms with transparent history.
