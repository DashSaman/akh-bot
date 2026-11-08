# 00-CURRENT-STATUS — dated audit checkpoints (Telegram-only)

## Native Persian routing — 2026-11-08 / مسیر خبر فارسی

- فارسی: تشخیص زبان متن فارسی دارای نام لاتین و عربی دارای «آ» اصلاح شد. فارسی روشن بدون ترجمه حفظ و وضعیت ترجمه در پیش‌نویس ثبت می‌شود. ناظر ترجمه، نسخهٔ فارسی اصلی را صرفاً به‌دلیل گزارش خارجی متفاوت بازترجمه نمی‌کند. متن مبهم و خارجی همچنان کنترل انتشار دارند؛ صف تاریخی به‌صورت گروهی بازگردانده نشد.
- English: content syntax replaces single-letter assumptions for routing. Clear Persian with Latin entities stays native; Arabic mislabeled fa gets the Arabic model route. V2 persists translation provenance; QA recognizes native originals instead of retranslating them against a different foreign report. Ambiguous/foreign copy remains gated. See `docs/incidents/2026-11-08-native-persian-routing.md`.
- Android cleanup, explicitly requested after the prior retention checkpoint: no dedicated Android container existed. Unused SDK, AVD/emulator and matching temporary assets removed (~287 MiB allocated); only idle ADB port 5037 closed. Existing 2-id application/API/Postgres containers and other services remained running with unchanged IDs/start times/restarts; API health HTTP 200. فارسی: حذف اندروید با حفظ سرویس‌های فعال و کنترل اتصال/پردازش انجام شد؛ فایل ۶ GiB پراکنده فقط بخشی از فضای واقعی حذف‌شده بود.
- Code validation and deployment: pending the current isolated Linux full-suite run; the previous live release remains the checkpoint below until rollout verification.

## Final verified release — 2026-11-08 / نسخهٔ نهایی بررسی‌شده

- **Current live image:** `akhbot-app:quality-50fa9e5`; app and watcher revision `50fa9e569f2d48765ee3f46aded48e692d1d9362`. App healthy/HTTP 200, watcher running, zero restarts. All 99 app Python/SQL files matched the release source (line endings normalized). PRs #12 and #13 are merged.
- **Tests:** complete isolated Linux suite **547 PASS**, 24 existing deprecation warnings; 53 focused publisher/QA/media regressions PASS. GitHub CI for the deployed code succeeded. Runtime offline smoke rejected notices, mixed-script words and cut-off leads across all four publisher paths, preserved a valid complete long story and created no public job for failed QA repair.
- **Pause restored:** 14:43:24 UTC. Nine valid current-version jobs missed during the controlled pause were requeued after checking their pending publication, hash, current variant and copy quality. All nine subsequently completed; four actual SENT ledger updates and seven quality/policy SKIPs were observed across work after resume. Completed jobs alone are not counted as public sends.
- فارسی: نسخهٔ نهایی روی هر دو سرویس فعال و سالم است؛ ۵۴۷ آزمون کامل و ۵۳ آزمون مرتبط موفق بود. متن خطا، نام مخلوط و جملهٔ بریده رد می‌شود. کپشن بلند به پیام متنی کامل تبدیل می‌شود؛ متن یا ویرایش بیش‌ازحد بلند به‌جای بریده‌شدن متوقف می‌شود. توقف موقت برداشته شد و هر ۹ کارِ معتبرِ وقفه پس از کنترل دوباره پردازش شد.
- Cleanup and backup evidence is in the earlier checkpoint below. Baseline service units and TCP listeners were retained. Other tasks were independently deploying/auditing the reseller project, so later container count/free space changed outside this news rollout. No foreign service was stopped by this task.
- فارسی: پاک‌سازی به سرویس‌ها و ورودی‌های شبکه آسیب مشاهده‌شده‌ای نزد؛ عملیات هم‌زمان پنل فروشندگان/ممیزی آن، خارج از این کار بود. پشتیبان تازه و نسخه‌های بازگشت حفظ شدند. اعلان‌های تاریخیِ شناسایی‌شده کورکورانه حذف یا با متن تأییدنشده جایگزین نشدند.
- Remaining findings: the pre-existing daily cleanup timer is disabled; the live nine-router JSON log lacks rotation. The app health endpoint can time out during busy pipeline work (observed before and after rollout); the final recheck returned 200. Historic latest-payload flags require direct editorial review; these deterministic checks do not prove semantic correctness of every article.
- فارسی: موارد باقی‌مانده شامل زمان‌بند پاک‌سازیِ از قبل غیرفعال، لاگ زندهٔ بدون چرخش nine-router و پاسخ‌گویی گاه‌به‌گاه کند صفحهٔ سلامت هنگام پردازش است. پیام‌های تاریخیِ علامت‌خورده به بازبینی مستقیم نیاز دارند؛ کنترل‌های قطعی جای فهم کامل معنایی همهٔ خبرها را نمی‌گیرند.

## 2026-11-08 publication-quality and safe-disk checkpoint

- Follow-up: a malformed mixed-script/fragmented translation was found in a completed job, but its publication was SKIPPED by materiality (no remote ID). Independent readability checks now reject that pattern before it can rely on an unrelated gate. Focused regressions: 34 PASS; full Linux/deployment results follow in the incident record.
- فارسی: موردِ ترجمهٔ بریده در صف پیدا شد، ولی منتشر نشده بود. کنترل مستقل واژهٔ مخلوط و بند ناقص اضافه شد؛ ۳۴ آزمون متمرکز موفق بود. وضعیت پایان‌یافتهٔ کار، دیگر در بررسی عملیاتی با ارسال واقعی اشتباه گرفته نمی‌شود.

- فارسی: ریشهٔ اعلان عمومی «اشکال در ترجمه» در ناظر مستقل کیفیت پیدا شد: شکست اصلاح، یک ویرایش عمومیِ اعلان خطا تولید می‌کرد. اکنون شکست فقط HOLD داخلی می‌شود؛ اعلان خطا، امتناع مترجم و اعلانِ صرف برنامهٔ رادیویی در مرزهای انتشار نیز مسدود می‌شوند. صف قدیمی و کش ترجمه دوباره کنترل می‌شوند. اصلاح قدیمی ناظر حق بازنویسی نسخهٔ جدیدتر خبر را ندارد.
- English: the independent QA watcher queued a public translation-review notice when repair failed. Failure now records an internal hold. Shared copy checks reject operational notices/refusals and broadcast-only announcements in translation/cache, queue execution and all Telegram publisher paths. QA updates use optimistic version checks; duplicate jobs preserve existing SENT history.
- فارسی: پاک‌سازی با فهرست دقیق و کنترل پردازش/اتصال انجام شد: ۱۴۶ مورد موقت، ۱۳۲ ایمیج قدیمی و یک کش پژوهشیِ بدون استفاده حذف شدند؛ ۵ رکورد ایمیج دیگر توسط خود Docker همراه وابستگی‌های آزاد حذف شده بودند. نسخه‌های فعال و اخیر، پایگاه‌های داده و دیسک Android حفظ شدند. فضای آزاد از حدود ۵۹۴ MiB به ۳٫۹ GiB رسید؛ ۱۰ کانتینر، ۳۴ سرویس و ۴۵ ورودی TCP بدون ریستارت حفظ شدند.
- English: manifest-based cleanup removed 146 disposable temporary entries, 132 old unused image records and one unused sparse research cache; Docker had already removed five further parent records during dependency cleanup. Active/recent rollback images, databases and Android state were retained. Free space rose from ~594 MiB to ~3.9 GiB; snapshots show unchanged 10 running containers, 34 services and 45 TCP listeners, with no restart during cleanup.
- Verification: 26 focused regressions PASS; complete isolated Linux suite **533 PASS** (24 existing deprecation warnings). Windows full-suite baseline had three platform failures (two POSIX deployment-script tests and symlink privilege). Linux harness normalizes checkout shell-script line endings and uses temporary bootstrap data, without production volumes or credentials.
- Read-only reconstruction from each story's latest SENT payload found 13 suspect historical messages: 8 translation-review notices and 5 broadcast-only announcements. This is ledger evidence, not direct confirmation of current Telegram contents; no blind replacement/deletion was performed.
- Remaining operational findings: the existing daily cleanup timer was already disabled; it was not silently re-enabled. nine-router has a large live JSON log without configured rotation; it was not truncated or restarted.
- Follow-up complete-copy change: a story too long for a media caption falls back to one complete text message. Oversized text and caption edits are blocked without slicing a sentence; permanent publisher rejections are SKIPPED rather than retried. فارسی: خبر بلند به‌جای کپشن بریده، کامل و متنی فرستاده می‌شود؛ متن یا ویرایش بیش‌ازحد بلند متوقف و از تکرار بی‌فایده جلوگیری می‌شود.
- Live rollout completed on 2026-11-08 at 14:14 UTC: app and QA watcher both use `akhbot-app:quality-065843d`, revision `065843d889878d3494da1e22ad424627d62865d8`. App healthy, watcher running, both restart counts zero. GitHub PR #12 CI succeeded. Runtime no-network smoke passed all four invalid-copy boundaries, allowed a valid story, and confirmed zero public jobs for failed QA repair in a temporary DB.
- فارسی: نسخهٔ اصلاح‌شده روی هر دو سرویس فعال شد؛ سرویس خبر سالم و ناظر فعال است. نسخهٔ قبلی برای بازگشت و پشتیبان فشردهٔ تازه با کنترل SQLite/gzip نگه داشته شد. فضای آزاد پس از این پشتیبان حدود ۳٫۳ GiB بود. همهٔ ورودی‌های TCP و سرویس‌های پایه حفظ شدند؛ پنل فروشندگان هم‌زمان توسط چت جداگانهٔ خودش استقرار داشت و در این عملیات تغییر داده نشد.
- English: prior containers remain stopped for rollback. A fresh 1.40 GB SQLite online backup passed quick_check and gzip verification (compressed ~355 MB). Final free space was ~3.3 GiB after backup/build. All baseline service units and TCP listeners remained. A separate concurrent reseller-dashboard task independently deployed that panel; this task changed only the two news services.
- See docs/incidents/2026-11-08-public-translation-notices.md. No synthetic public canary was posted; the runtime smoke used MockTransport and a temporary DB.

## 2026-10-12 independent reconciliation / FCC decision
- **Repository HEAD:** c907d716 at the documented 2026-10-12 source-sync checkpoint (for the latest SHA, use git rev-parse HEAD and GitHub CI).
- **Production runtime SHA:** edd819a (**historical 2026-10-06 only**, NOT the current running image SHA); current image revision remains **UNVERIFIED** because its metadata lacks an immutable Git revision label.
- GitHub/main and server main reached the **same source Git tree** at source-sync commit 363ba05a, with all 15 formerly local-only commits and reviewed tracked/untracked hotfixes preserved. The original 15-commit head remains under archive/rasteh-server-pre-sync-20261012; dirty-state backup at /opt/akhbot/backups/rasteh-sync-20261012T0048Z.
- GitHub CI for 363ba05a: **GREEN** (test and Docker jobs). Isolated worktree suite: **483 passed**; governance: **59 DONE / 2 BLOCKED_EXTERNAL**.
- This is **source parity**, not proof of the *running Docker image SHA*: the existing akhbot-app:liveblog-20261009 image is healthy but has no immutable Git revision label. No service restart/deployment took place as part of this source reconciliation.
- Read-only runtime audit: DB integrity OK, 3,793 historical SENT ledger records, no pending jobs, no failed jobs in last 6 hours (two in 24 hours), and most recent observed SEND remote_id=2187 at 2026-10-11T13:05Z. Observations are point-in-time, not continuous guarantees.
- Translation backlog inventory: 172 active backoffs and 1,915 events with historical attempts; do not blindly requeue old or HELD events.
- Free Claude Code (FCC) source reviewed, **not installed/deployed**: Python 3.14.7 requirement; AGPL-3.0-only; model catalog mixes free, paid and subscription routes. Controlled no-DB 9Router probes: ZAI Arabic one fixture PASS (~19s); Groq English and Cloudflare Hebrew HTTP 503; Qwen Arabic lost uncertainty. **No new provider qualified or promoted**. See docs/research/FCC-ZERO-COST-TRANSLATION-2026-10-12.md and scripts/benchmark_zero_cost_translation.py.
- Host disk at audit **95% used**: do not deploy/build additional production images or prune global Docker resources without a scoped space/safety plan. All unrelated shared-host services remained untouched.
- Product publication scope remains **Telegram @RastehNews ONLY**, no paid X/social publishing.

## Historical release checkpoint — 2026-10-04 to 2026-10-09

## Emergency public-format hotfix — 2026-10-09 / اصلاح اضطراری قالب عمومی
- Production `akhbot-app` omitted the owner's decided `config/brand.yml`, resulting in the stale «پیش‌نمایش سکوی خبری» footer. Restored runtime config, added a persistent brand-config mount to docker-run/compose, and fail-closed public-brand checks.
- 87 unique @RastehNews messages carrying the preview footer were edited in place (160 ledger revisions); no replacement posts. One-time repair script saves original variants under `/data/backups/`.
- Removed duplicated truncated headlines/leads and source promotional lines at render time. Additional historic duplicate-only messages are being audited separately; do not claim completion until edit API responses confirm it.
- فارسی: فایل برند اصلی به کانتینر بازگردانده شد؛ امضای آزمایشی ممنوع شد، ۸۷ پیام قبلی در همان شناسه ویرایش شدند و اصلاح تکرار متن خبر به قالب اضافه شد.


The following lines are the historical 2026-10-06 freeze values, not today's runtime source of truth. History and later fixes are preserved in Git.

- **Repository HEAD (historical):** edd819a (deployed code commit; docs-only follow-up may be newer)
- **Production runtime SHA (historical):** edd819a (deployed healthy 2026-10-06)
- **Governance:** PASS — 59 DONE / 0 PARTIAL / 2 BLOCKED_EXTERNAL
- **Parts:** PART 1 = PASS - PART 2 = BLOCKED_EXTERNAL - PART 3 = PASS - PART 4 = PASS - PART 5 = PASS - PART 6 = PASS - PART 7 = PASS - PART 8 = BLOCKED_EXTERNAL - PART 9 = PASS - PART 10 = PASS
- **Publication ledger SENT: **474**** (historical freeze snapshot; live ledger may be higher)
- **Tests:** 435/435 (full local regression suite, 2026-10-06)

## Scope (FINAL, frozen)
INGEST many sources -> normalize -> verify -> Iran-first priority ->
dedup/Event/Story -> original media when available -> **publish ONLY to
Telegram @RastehNews**. No automatic X/Threads/Facebook/Instagram posting
(ledger is 100% telegram, 1435+ rows). X / Truth Social remain INPUT sources
only; LIMITED_X_ACCESS is not a release blocker; no paid social APIs.

## Caps (effective runtime)
MAX_NEW_POSTS_PER_DAY=500, MAX_NEW_POSTS_PER_HOUR=60, lifecycle
provisional=45 / confirmed=60 (never cut global capacity). Edits consume
ZERO new-post capacity (created_at filter). 500/day is a ceiling, never a
quota — low-value content never fills it.

## Editorial quality
- Iran-first ~90% soft allocation with natural spill (never fabricated).
- IRAN_CRISIS_MODE: correct state machine; verification NEVER weakens.
- Hard quality gates: HOLD_ABUSIVE, CONTEXT_INCOMPLETE, LOW_VALUE_CONTENT,
  LOW_MATERIALITY, MATERIALITY_FLOOR, DROP_DUPLICATE, HOLD_TRANSLATION_QUALITY
  — enforced at ENQUEUE and re-enforced at SEND time.
- Translation: EN prefers GPT-OSS-120B; AR prefers Qwen3.8-27B. Both then
  use validated Cloudflare/Mistral Small 3.1, then Z.AI GLM-4.5-Flash, before
  the generic `rasteh-translation` combo. Provider failure remains fail-closed.
- One event = one story = one SEND; material updates EDIT the same post
  (remote_id preserved); non-material duplicates DROP.

## Source management (self-service, DB-driven, no restart)
/admin/sources (+edit/test/audit) and bot commands (/sources /addsource
/enablesource /disablesource /testsource) with can_manage_sources;
SSRF-guarded normalization; duplicate-endpoint merge; canonical identity
(polling priority != trust); publication_policy AUTO/VERIFY_ONLY/
DISCOVERY_ONLY/NEVER_PUBLISH. @caronline_original OWNER_ENABLED, identity
CarOnline, fetching live.

## Multi-admin editorial bot
Numeric-user_id auth (bot_admins); text/forward/photo/video/album intake ->
held RawItems -> SAME canonical pipeline on approval; no direct-send bypass;
album debounce; file_id-only media (zero permanent binaries).

## Media policy
Original source media via file_id/URL ladder; no branded cards
(MEDIA_FALLBACK_CARDS_ENABLED=false, 0 branded assets); temp deleted
success/failure; media failure degrades to text-only.

## Watchdogs
PUBLICATION_PIPELINE_STALLED, IRAN_PUBLICATION_PIPELINE_STALLED,
SOURCE_MONOPOLY_DETECTED, SOURCE_STARVATION — warn/diagnose only.

## Remaining external limitations
- X posting: owner cost policy (Pay-Per-Use declined) — input-only.
- Truth Social RSS: Cloudflare-blocked server-side.
- Threads: account suspended pending human review.
- Mistral/Qwen consoles: phone verification walls.
