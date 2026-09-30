# Runtime Data / داده زمان‌اجرأ

- `akhbot_data:/data/akhbot.db` — THE state (sources+watermarks, events, stories/versions, publication ledger, jobs). **Migration-critical.**
- `/data/backups/` — online backups, 14-day retention. Transfer-safe.
- `/data/reports/soak-metrics.jsonl` — 24h soak metrics (service-collected).
- `/data/media-cache/` — TEMPORARY media. **NOT migration data** (hash+rights+remote IDs live in DB).
- Secrets (`/opt/akhbot/.env`, Telethon session): NEVER in backups/git — manual protected transfer.

# فارسی
- دیتابیس = همه وضعیت (اجباری برای مهاجرت) · بکاپ‌ها امن · سنجه‌های تست ۲۴ساعته · کش مدیا موقتی (منتقل نمی‌شود) · رمزها خارج از بکاپ/گیت.
