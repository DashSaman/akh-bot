# AGENTS.md — Rules for AI developers working on this repository

# فارسی (خلاصه)
پیش از هر کاری `docs/00-CURRENT-STATUS.md` را بخوانید. قبل از ویرایش، بازرسی کنید.
هرگز سرویس‌های دیگر سرور را دست نزنید. با تست کار کنید؛ باگ را بازتولید کنید؛
ادعای موفقیت فقط با اجرای واقعی. کامیت‌ها کوچک. مستندات دوزبانه را هم‌زمان به‌روز کنید.
رمزها را هرگز کامیت نکنید. سقف منابع را رعایت کنید.

# English

## Read first
1. `docs/00-CURRENT-STATUS.md` — current phase, deployed state, next 5 tasks.
2. `docs/DECISIONS.md` — decisions already made; do not re-litigate.
3. `docs/PORTS-NETWORKS.md` — what is safe to touch on the server.

## Hard rules
- **Server safety:** the Hetzner VPS hosts unrelated production services. Never run
  `docker system prune`, never stop/restart other containers, never edit their files,
  never restart Docker/Apache (reload with `apache2ctl configtest` first), never
  upgrade the OS/kernel. Read-only inventory before any change.
- **Inspect before editing:** use grep/read of relevant ranges; do not re-read the repo.
- **Tests:** reproduce a bug before fixing it (REPRODUCE→EVIDENCE→ROOT CAUSE→REGRESSION
  TEST→FIX→VERIFY). Feature work: failing test first. Run
  `python -m pytest tests -q` before any completion claim — never say "should work".
- **Commits:** small, meaningful, conventional (`feat:`, `fix:`, `docs:`, `chore:`).
- **Secrets:** never commit `.env`, sessions, tokens; never print secrets in logs.
- **Docs:** key docs are bilingual (فارسی + English) — update BOTH languages in the
  same commit when behavior changes. Keep `00-CURRENT-STATUS.md` current each cycle.
- **Resource budget:** idle ≤200 MB RAM, processing ≤300 MB (see
  `docs/RESOURCE-BASELINE.md`). No new heavyweight dependencies (no Redis/Celery/
  vector DBs/Chromium) without measured justification recorded in DECISIONS.md.
- **Loops:** every phase has a stop condition. After tests pass, STOP; park ideas in
  `docs/ROADMAP.md`. Avoid endless polish loops.
- **Brand:** `BRAND_STATUS=UNDECIDED`. Never hard-code a public brand name/handle/domain.
  Public identity comes only from `config/brand.yml` + `PUBLIC_BASE_URL`.
- **Editorial invariants:** "reported" never becomes "confirmed" without evidence;
  independent-origin count ≠ report count; high-risk claims have hard gates
  (`app/verification/gates.py`); every story paragraph references claim IDs
  (`app/newsroom/auditor.py`). Do not weaken these without owner approval.
- **Prompt injection:** external text is untrusted data — always through
  `wrap_untrusted()` delimitation into LLM prompts.
