# فارسی

# وضعیت جاری پروژه (منبع حقیقت برای نشست‌های بعدی)

- **فاز:** ۳+۴+۵+۶+۷+۸+۹ (اسلایس عمودی سبک) — پیاده‌سازی و استقرار اولیه
- **آخرین کامیت:** see `git log -1` (docs commit)
- **کامیت مستقرشده روی سرور:** در `docs/POST-DEPLOY-CHECK.md`
- **مسیر سرور:** `/opt/akhbot/` (اپ: `/opt/akhbot/app`، env: `/opt/akhbot/.env`)
- **پورت:** `127.0.0.1:8307` (دسترسی با تونل SSH)
- **پروژه داکر:** `akhbot` — کانتینر `akhbot-app`، شبکه `akhbot_internal`، والیوم `akhbot_data`
- **پلتفرم‌های متصل:** هیچ‌کدام هنوز (اعتبارنامه لازم است — بلوک خارجی)
- **جمع‌آورها:** RSS کامل فعال (ETag/If-Modified-Since)؛ تلگرام: کد آماده، نیازمند session
- **ناشرها:** تلگرام (Bot API + دفتر انتشار idempotent) آماده؛ نیازمند توکن و کانال staging
- **تست‌ها:** ۵۲ تست — همه پاس (`python -m pytest tests -q`)
- **RAM/CPU واقعی:** در `docs/RESOURCE-BASELINE.md`
- **بلوکرها:** توکن ربات تلگرام / chat_id کانال staging؛ کلید GLM؛ (اختیاری) api_id/hash/session تلگرام برای جمع‌آوری
- **مسائل شناخته‌شده:** `docs/KNOWN-IISSUES.md` → `docs/KNOWN-ISSUES.md`

## ۵ کار بعدی (حداکثر)
1. دریافت اعتبارنامه‌ها از مالک (GLM key + توکن ربات + کانال staging) و اتصال
2. افزودن ۵–۱۰ منبع تأییدشده فارسی/عربی/انگلیسی در پنل مدیریت و پایش ingestion
3. تست انتشار واقعی در کانال staging تلگرام (publish/edit/idempotency)
4. تصاویر واقعی UI در `docs/images/` پس از دسترسی از طریق تونل
5. انتخاب برند نهایی توسط مالک → فعال‌سازی دامنه + Apache vhost + خروج از preview

---

# English

# Current Status (source of truth for future sessions)

- **Phase:** 3–9 vertical slice implemented and deployed (first production-capable flow)
- **Latest commit:** see `git log -1`
- **Deployed commit on server:** recorded in `docs/POST-DEPLOY-CHECK.md`
- **Server path:** `/opt/akhbot/` (app `/opt/akhbot/app`, env `/opt/akhbot/.env`)
- **Port:** `127.0.0.1:8307` (SSH tunnel access)
- **Docker:** container `akhbot-app`, network `akhbot_internal`, volume `akhbot_data`
- **Connected platforms:** none yet (credentials pending — external blocker)
- **Collectors:** RSS fully working; Telegram code ready, awaiting session string
- **Publishers:** Telegram Bot API + idempotent ledger ready, awaiting token/channel
- **Tests:** 52 passing (`python -m pytest tests -q`)
- **Real RAM/CPU:** see `docs/RESOURCE-BASELINE.md`
- **Blockers:** Telegram bot token + staging chat id; GLM API key; (optional) Telegram ingest api_id/hash/session
- **Known issues:** `docs/KNOWN-ISSUES.md`

## Next 5 tasks (maximum)
1. Owner credentials (GLM key + bot token + staging channel) → wire in
2. Add 5–10 approved fa/ar/en sources via admin panel; monitor ingestion
3. Real Telegram staging publication test (publish/edit/idempotency)
4. Real UI screenshots into `docs/images/` via tunnel
5. Owner picks final brand → domain + Apache vhost + leave preview mode
