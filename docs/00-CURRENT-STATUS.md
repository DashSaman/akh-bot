# 00-CURRENT-STATUS — RUNTIME TRUTH (release-freeze 2026-10-04, v1.0.0-telegram)

One current truth. History lives in git.

- **Repository HEAD:** c674510
- **Production runtime SHA:** c674510 (deployed, healthy; CI green on this SHA)
- **Governance:** PASS — 59 DONE / 0 PARTIAL / 2 BLOCKED_EXTERNAL
- **Parts:** PART 1 = PASS - PART 2 = BLOCKED_EXTERNAL - PART 3 = PASS - PART 4 = PASS - PART 5 = PASS - PART 6 = PASS - PART 7 = PASS - PART 8 = BLOCKED_EXTERNAL - PART 9 = PASS - PART 10 = PASS
- **Publication ledger SENT: **474**** (live ledger; edits never count)
- **Tests:** 414/414 (clean GitHub checkout: compileall + pytest + governance + docker build)

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
