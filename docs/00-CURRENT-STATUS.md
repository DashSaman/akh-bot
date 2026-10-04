# 00-CURRENT-STATUS — RUNTIME TRUTH (2026-10-04 FINAL-HARDENING)

One current truth. Historical incident notes live in git history, not here.

- **Repository HEAD:** 3a24426
- **Production runtime SHA:** 3a24426 (quality-gates deploy 2026-10-04T16:4xZ; healthy; CI green)
  deploys after clean-checkout + CI green)
- **Governance:** PASS — tally: 59 DONE / 0 PARTIAL / 2 BLOCKED_EXTERNAL
- **Parts:** PART 1 = PASS - PART 2 = BLOCKED_EXTERNAL - PART 3 = PASS - PART 4 = PASS - PART 5 = PASS - PART 6 = PASS - PART 7 = PASS - PART 8 = BLOCKED_EXTERNAL - PART 9 = PASS - PART 10 = PASS
- **Tests:** full suite green in clean-checkout/CI runs

## Publishing
- Telegram @RastehNews is the ONLY publishing platform (owner decision:
  X API declined over Pay-Per-Use cost risk; the auto-created X developer
  app has NO card attached, zero balance, posts nothing).
- MAX_NEW_POSTS_PER_DAY=500, MAX_NEW_POSTS_PER_HOUR=60 — safety ceilings;
  lifecycle guards provisional=45/confirmed=60 never cut the global hourly
  capacity. Edits NEVER consume caps (created_at filter).
- Publication ledger SENT: **411** (2026-10-04 hardening baseline; live
  value in the admin dashboard).

## Editorial policy
- Iran-first ~90% soft allocation: P2/P3 defer one pass ONLY while rolling
  Iran share is under target AND Iran supply exists; capacity spills
  automatically; never fabricated.
- IRAN_CRISIS_MODE: triggers on two-plus distinct-source P0 Iran events in
  30 minutes; extends on fresh triggers; stays active until the calm window
  actually expires; translation budget doubles in crisis. Verification is
  NEVER weakened (order is not trust).
- Multi-admin editorial bot: numeric-id auth; submissions become held
  RawItems and flow the SAME canonical pipeline on approval; album debounce
  (one group = one submission + one preview); file_id-only media; forwards
  map canonical identity; unknown origins never gain trust.
- Admin UI: /admin/bot-admins + /admin/editorial-inbox (login + CSRF).

## Watchdogs
PUBLICATION_PIPELINE_STALLED | IRAN_PUBLICATION_PIPELINE_STALLED (10-minute
Iran liveness + bounded job nudge) | SOURCE_MONOPOLY_DETECTED |
SOURCE_STARVATION — warn/diagnose only; never auto-block; never fake posts.

## Sources
187 endpoints / 78 canonical identities; X + Truth Social endpoints are
truthfully LIMITED_X_ACCESS (no paid API; Truth Social RSS is
Cloudflare-blocked server-side). NAYA/Yashar: highest SPEED priority, normal
trust. Diversity soft guard: 25/45 percent rolling-hour canonical caps,
dominant-identity only, breaking always passes.

## AI pool (9Router, localhost-only)
Six-slot combo rasteh-translation across four companies: groq, cohere2,
groq, cf/mistral, openrouter, cf/llama8; direct-groq emergency fallback with
guaranteed json_object prompt; all-fail degrades to HOLD fail-closed.
