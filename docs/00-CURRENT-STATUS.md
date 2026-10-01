# 00-CURRENT-STATUS — RUNTIME TRUTH ONLY (2026-10-01 13:50Z)

- **Production SHA:** afcc60f (=repo HEAD؛ healthy؛ restart=unless-stopped؛ Docker enabled)
- **PART:** 1 EXECUTED (canonical core) — awaiting owner review; next plan: PART-02
- **Sources (allowlist ON):** 1=naya_foriraq 2=withyashar (OWNER_ENABLED/AUTO/30s)؛ بقیه OWNER_DISABLED
- **Collector mode:** Telegram=WEB_FALLBACK (TELETHON_AUTH_REQUIRED)؛ RSS idem for disabled feeds
- **Workers:** ingest/pipeline/reverify/jobs/watchdog/soak — همه تازه (<2min)
- **AI:** صفر ارائه‌دهنده (NOT_CONFIGURED) → DETERMINISTIC؛ محتوای غیرفارسی → HELD (بدون نشت)
- **Platforms:** Telegram LIVE (@RastehNews؛ 86 SENT mapped)؛ X=BLOCKED_BY_COST_POLICY؛ IG/Threads=AUTH_REQUIRED؛ FB=NOT_CONFIGURED؛ Web=PREVIEW
- **Media:** cache=0؛ sendPhoto/sendVideo+caption-gate DONE؛ مدیای اصلی منبع منتظر Telethon
- **Admin:** https://rasteh.softarg.ir (دو-لایه) سالم؛ sources/platforms/media زنده؛ AI/health/intake pages MISSING
- **Queue:** jobs done=153 failed=879(تاریخی/مهارشده)؛ SENT=86؛ HELD=59
- **PART-1 evidence:** migration 939/1027 converted (1 unsafe preserved), blob-headlines=0, GATE-11 last-20 SENT missing=0 dup=0, restart recovery fresh hb, SENT=89 unchanged integrity
- **⚠ Known BROKEN (Part 3):** سیل میکروپست — 986 story/1020 event از ۲ کانال؛ بدون burst/merge/completeness (REG-028..031/036..040)
- **Blockers:** کلید AI رایگان؛ Telethon session؛ OAuth متا؛ دامن عمومی
