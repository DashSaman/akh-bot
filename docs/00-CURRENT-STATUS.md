# 00-CURRENT-STATUS — dated audit checkpoints (Telegram-only)

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
