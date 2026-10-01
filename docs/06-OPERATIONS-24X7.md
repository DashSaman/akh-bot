# 06-OPERATIONS-24X7
(Runtime truth @9affb54 — detail spec, current values marked)

## Workers (همه داخل کانتینر akhbot-app، بدون عامل/مرورگر/SSH — INV-021)
ingest (≤30s loop; sweep=120s max, Tier-1=30s) · pipeline (60s) · reverify (300s, شامل HELD) · jobs (10s, priority+backoff) · watchdog (120s: heartbeat-staleness+orphan markers) · soak (600s metrics). Heartbeats: `settings.*_last_run` — همگی تازه در ممیزی.

## SLA / Recovery
- منبع: last_check/next_check از polling_interval_seconds؛ نقض → SOURCE_SLA_BREACH توسط watchdog
- یتیم: NEW>120s → شمارنده + پاس pipeline؛ هدف=۰ (الان ۰)
- Restart: `restart=unless-stopped`؛ jobs گیرکرده → requeue؛ اثبات‌شده چندین‌بار (ضربان‌ها برمی‌گردند، صفر پست تکراری)
- Backoff نمایی + jitter در jobs؛ هیچ حلقهٔ تنگ شکست نیست

## Collection modes
- Telegram: **WEB_FALLBACK** (t.me/s، watermark pagination، بدون از‌دست‌رفتن>صفحه) — Telethon بعد از session مالک: REALTIME NewMessage + ویرایش/حذف reconciliation (INGEST-003 BLOCKED_EXTERNAL)
- RSS: ETag/If-Modified-Since

## Degradation order (منبع محدود)
1) کار پس‌زمینهٔ اختیاری 2) مدیا/کش (downloads متوقف در disk critical) 3) AI اختیاری 4) هستهٔ متنی هرگز قربانی نمی‌شود (INV-020)

## Soak
SOAK_TEST_STARTED_AT=2026-09-30T17:38Z؛ سنجه‌ها در `/data/reports/soak-metrics.jsonl` توسط خود سرویس؛ doctor.sh/verify_instance.sh = سلامت تک‌فرمانی (خروج ۰).
