# فارسی

# عملیات روزمره

## پایش
```bash
docker ps --filter name=akhbot-app          # وضعیت + health
docker stats --no-stream akhbot-app         # RAM/CPU لحظه‌ای
docker logs --tail 50 akhbot-app            # لاگ JSON ساخت‌یافته
curl -s http://127.0.0.1:8307/ready         | وضعیت اتصال‌ها
```

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
`docker ps` / `docker stats akhbot-app` / `docker logs akhbot-app` / `curl /ready`
(readiness reports LLM/Telegram wiring state and brand status).

## Emergency pause
Admin → Settings → global or per-platform pause. Collectors keep collecting;
publishing stops (`settings` table: `pause_all`, `pause_platform:*`).

## Troubleshooting
See table in Persian section (source health, failed jobs, HELD events = intentional
high-risk gate, admin 429 = 15-min login lockout).

## Backup/restore
`scripts/backup_db.sh` (online backup + 14-day retention), `scripts/restore_db.sh`.
Restore must be exercised at least once (documented in TESTING.md).
