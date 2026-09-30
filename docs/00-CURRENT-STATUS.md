# فارسی

# وضعیت جاری پروژه (منبع حقیقت برای نشست‌های بعدی)

- **فاز:** 🟢 عملیات زنده راسته‌نیوز آغاز شد (2026-09-30) — ۱۰ منبع فعال، ۳ خبر منتشرشده در @RastehNews
- **GLM:** BLOCKED_EXTERNAL (کلید ارائه نشده) — تحریریه‌ی عامل (agent) جایگزین موقت نویسنده است
- **تلگرام تولیدی:** LIVE — کانال @RastehNews (ID -1004459746525)
- **جفت کامیت مخزن/ایمیج:** با `scripts/doctor.sh --check-drift` بگیرید (delta فقط-مستندات مجاز است)
- **وضعیت اجزا:** جمع‌آور RSS=LIVE_VERIFIED · نویسنده GLM=BLOCKED_EXTERNAL (بدون کلید) · ناشر تلگرام=BLOCKED_EXTERNAL · جمع‌آور تلگرام=WAITING_FOR_CREDENTIALS · X/IG/Threads=NOT_CONFIGURED · برند=UNDECIDED · ایندکس=PREVIEW(NOINDEX)
- **CI:** GitHub Actions (تست آفلاین + بیلد داکر) — بدون رمز، بدون تماس با سرور تولیدی
- **مسیر سرور:** `/opt/akhbot/` (اپ: `/opt/akhbot/app`، env: `/opt/akhbot/.env`)
- **پورت:** `127.0.0.1:8307` روی سرور — دسترسی توسعه با تونل SSH (پورت محلی 18307)
- **پروژه داکر:** کانتینر `akhbot-app`، شبکه `akhbot_internal`، والیوم `akhbot_data`
- **پلتفرم‌های متصل:** وب (preview)؛ تلگرام/GLM در انتظار اعتبارنامه
- **جمع‌آورها:** RSS ✅ فعال و تست‌شده زنده (BBC Persian)؛ تلگرام: کد آماده، نیازمند session
- **ناشرها:** تلگرام (Bot API + دفتر انتشار idempotent) آماده؛ نیازمند توکن و کانال staging
- **تست‌ها:** ۵۴ تست پاس محلی + E2E مرورگری تولیدی (ورود/RTL/همه صفحات/CSRF/توقف اضطراری/خروج/رمز غلط)
- **RAM/CPU واقعی:** در `docs/RESOURCE-BASELINE.md`
- **اعتبارنامه مدیر:** فقط هش scrypt در `.env`؛ گذرواژه واقعی فقط در فایل root-only سرور: `/opt/akhbot/admin-credential.txt` (chmod 400) — هرگز در گزارش/گیت/لاگ قرار نمی‌گیرد
- **بلوکرها:** توکن ربات تلگرام + chat_id کانال staging؛ کلید GLM؛ (اختیاری) api_id/hash/session تلگرام برای جمع‌آوری
- **مسائل شناخته‌شده:** `docs/KNOWN-ISSUES.md`

## ۵ کار بعدی (حداکثر)
1. دریافت اعتبارنامه‌ها از مالک (GLM key + توکن ربات + کانال staging) و اتصال
2. دریافت فهرست منابع تأییدشده از مالک (طبقه‌بندی پیشنهادی: OFFICIAL_PRIMARY / MAJOR_NEWSROOM / JOURNALIST / LOCAL_SOURCE / AGGREGATOR)
3. تست کنترل‌شده GLM: یک مقاله واقعی → نویسنده → ممیز → انتشار در کانال staging → تکرار بدون پست تکراری → ویرایش → توقف/فعال‌سازی
4. انتخاب برند نهایی توسط مالک → دامنه + Apache vhost (قالب آماده) + خروج از preview
5. اتصال X/Instagram/Threads پس از در دسترس‌شدن حساب‌ها

---

# English

# Current Status (source of truth for future sessions)

- **Phase:** 🟢 RastehNews LIVE operation started (2026-09-30) — 10 sources, 3 stories published to @RastehNews
- **GLM:** BLOCKED_EXTERNAL (no key) — agent-editorial substitution in use
- **Production Telegram:** LIVE — @RastehNews
- **Heads pair:** via `scripts/doctor.sh --check-drift` (docs-only deltas explicitly allowed)
- **Component states:** RSS=LIVE_VERIFIED · GLM writer=BLOCKED_EXTERNAL · Telegram publisher=BLOCKED_EXTERNAL · Telegram collector=WAITING_FOR_CREDENTIALS · X/IG/Threads=NOT_CONFIGURED · brand=UNDECIDED · indexing=PREVIEW(NOINDEX)
- **CI:** GitHub Actions (offline tests + Docker build) — no secrets, no production contact
  cycle; POST-DEPLOY-CHECK.md records the verified pair.
- **Server path:** `/opt/akhbot/` (app `/opt/akhbot/app`, env `/opt/akhbot/.env`)
- **Port:** `127.0.0.1:8307` ON THE SERVER — development access ONLY via SSH tunnel
  (local port 18307). `127.0.0.1` in your browser means YOUR machine, not the VPS.
- **Docker:** container `akhbot-app`, network `akhbot_internal`, volume `akhbot_data`
- **Connected platforms:** web (preview); Telegram/GLM awaiting credentials
- **Collectors:** RSS ✅ live-tested; Telegram code ready, awaiting session
- **Publishers:** Telegram Bot API + idempotent ledger ready, awaiting token/channel
- **Tests:** 54 passing locally + production browser E2E (login/RTL/all pages/CSRF/
  emergency pause/logout/wrong-password)
- **Admin credential:** scrypt hash only in `.env`; the actual password lives ONLY in
  the server's root-only file `/opt/akhbot/admin-credential.txt` (chmod 400) — never
  in reports, git, or logs.
- **Blockers:** Telegram bot token + staging chat id; GLM API key; (optional) Telegram ingest session
- **Known issues:** `docs/KNOWN-ISSUES.md`

## Next 5 tasks (maximum)
1. Owner credentials (GLM key + bot token + staging channel) → wire in
2. Owner-approved source list (suggested classes: OFFICIAL_PRIMARY / MAJOR_NEWSROOM /
   JOURNALIST / LOCAL_SOURCE / AGGREGATOR — approval belongs to the owner)
3. Controlled GLM test: one real article → writer → auditor → staging publish →
   retry (no duplicate) → edit → pause/resume proof
4. Owner picks final brand → domain + Apache vhost (template ready) + leave preview
5. X/Instagram/Threads adapters once accounts are available
