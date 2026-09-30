# فارسی

# وضعیت جاری پروژه (منبع حقیقت برای نشست‌های بعدی)

- **فاز:** ۳ تا ۹ کامل + استقرار + تست زنده جمع‌آوری
- **آخرین کامیت:** `3d2fe8b`
- **کامیت مستقرشده روی سرور:** `3d2fe8b` (تأییدشده در POST-DEPLOY-CHECK.md)
- **مسیر سرور:** `/opt/akhbot/` (اپ: `/opt/akhbot/app`، env: `/opt/akhbot/.env`)
- **پورت:** `127.0.0.1:8307` (دسترسی با تونل SSH)
- **پروژه داکر:** کانتینر `akhbot-app`، شبکه `akhbot_internal`، والیوم `akhbot_data`
- **پلتفرم‌های متصل:** وب (preview)؛ تلگرام/GLM در انتظار اعتبارنامه
- **جمع‌آورها:** RSS ✅ فعال و تست‌شده زنده (BBC Persian، ۲۹ آیتم واقعی، backfill OK)؛ تلگرام: کد آماده، نیازمند session
- **ناشرها:** تلگرام (Bot API + دفتر انتشار idempotent) آماده؛ نیازمند توکن و کانال staging
- **تست‌ها:** ۵۲ تست پاس محلی + تست دود تولیدی (ورود پنل/CSRF/رمز غلط 401/بکاپ)
- **RAM/CPU واقعی:** 45.9MiB / ≤0.31% (RESOURCE-BASELINE.md)
- **بلوکرها:** توکن ربات تلگرام + chat_id کانال staging؛ کلید GLM؛ (اختیاری) api_id/hash/session تلگرام برای جمع‌آوری
- **مسائل شناخته‌شده:** `docs/KNOWN-ISSUES.md`

## ۵ کار بعدی (حداکثر)
1. دریافت اعتبارنامه‌ها از مالک (GLM key + توکن ربات + کانال staging) و اتصال
2. افزودن ۵–۱۰ منبع تأییدشده فارسی/عربی/انگلیسی و پایش ingestion
3. تست انتشار واقعی در کانال staging تلگرام (publish/edit/idempotency)
4. تصاویر واقعی UI در `docs/images/` پس از دسترسی از طریق تونل
5. انتخاب برند نهایی توسط مالک → فعال‌سازی دامنه + Apache vhost + خروج از preview

---

# English

# Current Status (source of truth for future sessions)

- **Phase:** 3–9 complete + deployed + live ingestion tested
- **Latest commit:** `3d2fe8b`
- **Deployed commit on server:** `3d2fe8b` (verified in POST-DEPLOY-CHECK.md)
- **Server path:** `/opt/akhbot/` (app `/opt/akhbot/app`, env `/opt/akhbot/.env`)
- **Port:** `127.0.0.1:8307` (SSH tunnel access)
- **Docker:** container `akhbot-app`, network `akhbot_internal`, volume `akhbot_data`
- **Connected platforms:** web (preview); Telegram/GLM awaiting credentials
- **Collectors:** RSS ✅ live-tested (BBC Persian, 29 real items, backfill OK); Telegram code ready, awaiting session
- **Publishers:** Telegram Bot API + idempotent ledger ready, awaiting token/channel
- **Tests:** 52 passing locally + production smoke tests (login/CSRF/401/backup)
- **Real RAM/CPU:** 45.9 MiB / ≤0.31% (RESOURCE-BASELINE.md)
- **Blockers:** Telegram bot token + staging chat id; GLM API key; (optional) Telegram ingest session
- **Known issues:** `docs/KNOWN-ISSUES.md`

## Next 5 tasks (maximum)
1. Owner credentials (GLM key + bot token + staging channel) → wire in
2. Add 5–10 approved fa/ar/en sources; monitor ingestion
3. Real Telegram staging publication test (publish/edit/idempotency)
4. Real UI screenshots into `docs/images/` via tunnel
5. Owner picks final brand → domain + Apache vhost + leave preview mode
