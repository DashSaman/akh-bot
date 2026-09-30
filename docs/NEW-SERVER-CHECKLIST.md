# New-Server Checklist / چک‌لیست سرور جدید

1. `bash scripts/deploy.sh` (fresh clone, new volume)
2. `bash scripts/restore_db.sh <backup.db>`
3. `bash scripts/verify_instance.sh` → must exit 0
4. Check watermarks: `SELECT external_id, fetch_state FROM sources` — untouched
5. Telegram destination: `curl -s http://127.0.0.1:8307/ready` → telegram_publish CONFIGURED; validate target is type=channel
6. Ledger intact: publications SENT rows keep remote_id + chat_id → no reposts
7. Observe ≥3 cycles: `*_last_run` heartbeats advance; no duplicate channel posts
8. AI keys absent → DETERMINISTIC_MODE (expected, healthy)
9. Telethon absent → WEB_FALLBACK + TELETHON_AUTH_REQUIRED (expected)

# فارسی
deploy → restore → verify_instance (خروج ۰) → بررسی watermarkها → مقصد تلگرام کانال → دفتر انتشار سالم → ≥۳ چرخه ضربان → AI غایب=DETERMINISTIC → بدون session=WEB_FALLBACK.
