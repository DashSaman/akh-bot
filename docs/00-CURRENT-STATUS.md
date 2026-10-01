# 00-CURRENT-STATUS — RUNTIME TRUTH ONLY (2026-10-01 13:50Z)

- **Production SHA:** 69059ab (verified in-container @PART-2) (=repo HEAD؛ healthy؛ restart=unless-stopped؛ Docker enabled)
- **PART:** 1 = PASS (validator-enforced) · **PART 2 = BLOCKED_EXTERNAL** (all actionable T1/T2-mock/T3 DONE+deployed; INGEST-003 awaits owner Telethon session for live <5s proof; WEB_FALLBACK authoritative @30s Tier-1)
- **سنجه‌های متمایز زمان-اجرأ (@6956ece):** Publication ledger SENT: **89** · Jobs DONE: **156** · تلگرام remote نگاشت‌شده (SENT با remote_id در کانال): **86** — سه متریک متمایز؛ «SENT» بدون پیشوند یعنی لجر
- **Sources (allowlist ON):** 1=naya_foriraq 2=withyashar (OWNER_ENABLED/AUTO/30s)؛ بقیه OWNER_DISABLED
- **Collector mode:** Telegram=WEB_FALLBACK (TELETHON_AUTH_REQUIRED — listener deployed, mock-proven, inactive w/o session)؛ checkpoints: naya ck=92254/wm=92254 · yashar ck=24680/wm=24680 (monotonic, restart-surviving; SLA breach keys=[]: هر دو سالم)
- **Workers:** ingest/pipeline/reverify/jobs/watchdog/soak — همه تازه (<2min)
- **AI:** صفر ارائه‌دهنده (NOT_CONFIGURED) → DETERMINISTIC؛ محتوای غیرفارسی → HELD (بدون نشت)
- **Platforms:** Telegram LIVE (@RastehNews؛ 86 SENT mapped)؛ X=BLOCKED_BY_COST_POLICY؛ IG/Threads=AUTH_REQUIRED؛ FB=NOT_CONFIGURED؛ Web=PREVIEW
- **Media:** cache=0؛ sendPhoto/sendVideo+caption-gate DONE؛ مدیای اصلی منبع منتظر Telethon
- **Admin:** https://rasteh.softarg.ir (دو-لایه) سالم؛ sources/platforms/media زنده؛ AI/health/intake pages MISSING
- **Queue:** jobs done=153 failed=879(تاریخی/مهارشده)؛ SENT=86؛ HELD=59
- **PART-1 evidence:** migration 939/1027 converted (1 unsafe preserved), blob-headlines=0, GATE-11 last-20 SENT missing=0 dup=0, restart recovery fresh hb, ledger SENT=89 (tg-remote=86) unchanged integrity
- **⚠ Known BROKEN (Part 3):** سیل میکروپست — 986 story/1020 event از ۲ کانال؛ بدون burst/merge/completeness (REG-028..031/036..040)
- **Blockers:** کلید AI رایگان؛ Telethon session؛ OAuth متا؛ دامن عمومی
