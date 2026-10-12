# 00-CURRENT-STATUS — RUNTIME TRUTH (release-freeze 2026-10-04, v1.0.0-telegram)

## Emergency public-format hotfix — 2026-10-09 / اصلاح اضطراری قالب عمومی
- Production `akhbot-app` omitted the owner's decided `config/brand.yml`, resulting in the stale «پیش‌نمایش سکوی خبری» footer. Restored runtime config, added a persistent brand-config mount to docker-run/compose, and fail-closed public-brand checks.
- 87 unique @RastehNews messages carrying the preview footer were edited in place (160 ledger revisions); no replacement posts. One-time repair script saves original variants under `/data/backups/`.
- Removed duplicated truncated headlines/leads and source promotional lines at render time. Additional historic duplicate-only messages are being audited separately; do not claim completion until edit API responses confirm it.
- فارسی: فایل برند اصلی به کانتینر بازگردانده شد؛ امضای آزمایشی ممنوع شد، ۸۷ پیام قبلی در همان شناسه ویرایش شدند و اصلاح تکرار متن خبر به قالب اضافه شد.


One current truth. History lives in git.

- **Repository HEAD:** edd819a (deployed code commit; docs-only follow-up may be newer)
- **Production runtime SHA:** edd819a (deployed healthy 2026-10-06)
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
