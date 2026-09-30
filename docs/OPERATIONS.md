# فارسی

# عملیات روزمره

## پایش
```bash
bash /opt/akhbot/app/scripts/doctor.sh              # وضعیت کامل بدون رمز
bash /opt/akhbot/app/scripts/doctor.sh --check-drift  # هم‌ارزی کد مخزن/ایمیج (delta فقط-مستندات مجاز)
bash /opt/akhbot/app/scripts/check_parity.sh        # هم‌ارزی docker run ↔ docker-compose
docker logs --tail 50 akhbot-app                    # لاگ JSON ساخت‌یافته
curl -s http://127.0.0.1:8307/ready                 # وضعیت اتصال‌ها
```

## فعال‌سازی اعتبارنامه‌ها (GLM + تلگرام staging)
1. مقادیر را فقط در `/opt/akhbot/.env` اضافه کنید (هرگز در گیت/لاگ):
   `GLM_API_KEY`، `GLM_MODEL` (مطابق حساب مالک)، `TELEGRAM_BOT_TOKEN`، `TELEGRAM_STAGING_CHAT_ID`
   و اختیاری: `TELEGRAM_INGEST_API_ID/_API_HASH/_SESSION`
2. `chmod 600 /opt/akhbot/.env && cd /opt/akhbot/app && bash scripts/deploy.sh`
3. راستی‌آزمایی کم‌هزینه (بدون چاپ رمز — فقط model/HTTP/latency):
   `docker exec -i akhbot-app python - < scripts/verify_integrations.py`
   - GLM: یک درخواست ping کوچک → LIVE_VERIFIED/ERROR
   - تلگرام: getMe + getChat + ارسال/ویرایش/حذف پیام تست [STAGING TEST] → LIVE_VERIFIED
   - نتیجه در settings ثبت می‌شود و داشبورد وضعیت را LIVE_VERIFIED نشان می‌دهد.
4. ران‌بوک E2E پس از تأیید (منبع امن کم‌ریسک → رویداد → ادعا → نویسنده → ممیز →
   انتشار staging → اجرای مجدد job (بدون دوبله) → ویرایش نسخه جدید → توقف/از سرگیری).

## کلید توقف اضطراری
پنل → تنظیمات → «فعال‌سازی توقف کل انتشار». جمع‌آوری ادامه می‌یابد؛ انتشار متوقف می‌شود.
(جدول `settings`: `pause_all` / `pause_platform:<p>`)

## خطاهای رایج
| نشانه | بررسی |
|---|---|
| منبع قرمز/سلامت پایین | `/admin/sources` → last_error؛ فید نامعتبر یا timeout |
| job های failed | `/admin` جدول کارها → last_error (مثلاً توکن تلگرام) |
| رویداد HELD | عمدی: تلفات متعارض/تک‌منبعی — `/admin/events/<id>` |
| پنل 429 | قفل ۱۵ دقیقه پس از ۵ ورود ناموفق |

## بکاپ/بازیابی
`scripts/backup_db.sh` (بکاپ آنلاین + نگهداشت ۱۴ روز) / `scripts/restore_db.sh <file>`.
تست بازیابی حداقل یک‌بار انجام شود (فرایند در TESTING.md).

---

# English

# Operations

## Monitoring
```bash
bash scripts/doctor.sh               # full no-secrets status snapshot
bash scripts/doctor.sh --check-drift # repo/image code equivalence (docs-only delta OK)
bash scripts/check_parity.sh         # docker run ↔ docker-compose equivalence
docker stats akhbot-app / docker logs akhbot-app / curl /ready
```

## Credential activation (GLM + Telegram staging)
1. Add values ONLY to `/opt/akhbot/.env` (never in git/logs):
   `GLM_API_KEY`, `GLM_MODEL` (per owner account), `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_STAGING_CHAT_ID`; optional `TELEGRAM_INGEST_API_ID/_API_HASH/_SESSION`.
2. `chmod 600 /opt/akhbot/.env && bash scripts/deploy.sh`
3. Cheap verification (prints model/HTTP/latency only, never keys):
   `docker exec -i akhbot-app python - < scripts/verify_integrations.py`
   — GLM: tiny ping request; Telegram: getMe/getChat + post/edit/delete of a clearly
   marked [STAGING TEST] message. Results persist to settings and the dashboard
   flips to LIVE_VERIFIED.
4. Then follow the E2E runbook: safe low-risk item → event → claims → writer →
   auditor → staging publish → re-run job (must NOT duplicate) → edited story
   version → pause/resume proof.

## Emergency pause
Admin → Settings → global or per-platform pause. Collectors keep collecting;
publishing stops (`settings` table: `pause_all`, `pause_platform:*`).

## Troubleshooting
See table in Persian section (source health, failed jobs, HELD events = intentional
high-risk gate, admin 429 = 15-min login lockout).

## Backup/restore
`scripts/backup_db.sh` (online backup + 14-day retention), `scripts/restore_db.sh`.
Restore must be exercised at least once (documented in TESTING.md).
