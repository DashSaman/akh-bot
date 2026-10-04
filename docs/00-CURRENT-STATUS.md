# 00-CURRENT-STATUS — RUNTIME TRUTH (snapshot 2026-10-04 11:0xZ, media-closeout)

- **Repository HEAD:** b5b7b29 (GitHub main synced; server clean)
- **Production runtime SHA:** cf3ff5a → media-closeout deploy this session
- **PART:** 1=PASS · 2=BLOCKED_EXTERNAL · 3=PASS (V2 LIVE) · 4=PASS · 5=PASS (9Router LIVE) · 6/7/8/9/10 = executable work COMPLETE
- **Governance:** PASS — Matrix 59 DONE / 0 PARTIAL / 0 MISSING / 0 BROKEN / 2 BLOCKED_EXTERNAL

## Runtime snapshot
- Publication ledger SENT: **322** (telegram remote-mapped; duplicate-SEND violations 0)

## 2026-10-04 13:03Z silence incident — RESOLVED (cap deadlock, 5th cause)
Morning fix new_posts_since() still filtered on updated_at: lifecycle edits
UPDATE the single SENT row in place (no new row), so continuous edits kept the
hourly count >= cap forever — every publish_send THROTTLED, channel silent
13:03-13:53. Fix: filter on created_at (immutable enqueue moment). Verified
live: story 1295 SENT remote_id=491 at 13:53:11; watchdog stall self-cleared;
sends now drip under the genuine daily cap (120/24h reached by real volume).

## 2026-10-04 no-news incident — RESOLVED (4 stacked causes)
1. **Edits consumed post caps** (`38c7e16`): lifecycle edits refresh a SENT row's
   updated_at; the hourly/daily caps counted them, pushed sent_24h to
   MAX_POSTS_PER_DAY=120 by 08:19 and every real publish_send was THROTTLED +1h.
   Caps now count first sends only (`new_posts_since`).
2. **Cards lived in the ephemeral layer** (`e5bbf1b`): branded-card PNGs were written
   under /srv/data/media — every redeploy orphaned pending card sends (file-not-found
   FAILED). Cards now render into the akhbot_data volume (DATA_DIR/media) and
   send_media degrades to a clean TEXT-ONLY post if a media file is ever missing.
3. **Jobs loop could freeze** (`cf3ff5a`): a hung network call inside a handler stalled
   the whole publish loop for hours. Handlers now run under
   asyncio.wait_for(job_handler_timeout_seconds=180) — timeout = normal retry.
4. **Media-message edits dropped** (`ed81766`): lifecycle edits of sendPhoto posts used
   editMessageText (rejected by Telegram). Fallback to editMessageCaption.

## AI pool (9Router, localhost-only :20128)
- Combo **rasteh-translation** (6 slots, 4 companies): groq/qwen3.8-27b →
  cohere2/command-a-03-2025 (Cohere trial via compat node, 20/min 1k/month) →
  groq/gpt-oss-120b → cf/mistral-small-3.1-24b → openrouter/nemotron:free
  (daily 50-req quota, quota-aware model-lock observed) →
  cf/llama-3.1-8b-fp8-fast; emergency direct FreeAiRouter (groq, json_object
  prompt guaranteed); all-fail → HOLD (fail-closed, foreign leak 0).
  Failover A (groq→cohere) / B (all-dead→direct) proven 2026-10-04.
- Providers evaluated 20 / connected 6 (groq PRIMARY, cohere PRIMARY,
  cloudflare-ai emergency+primary-quality, openrouter emergency, llm7
  emergency-quality, ZAI paid-blocked); Gemini + NVIDIA BLOCKED_REGION;
  Cerebras/SambaNova/Z.AI-API BLOCKED_PAID; Mistral-console/Qwen phone-walls;
  OpenCode free models return empty content (re-validated); mimo-free hidden
  auth; Kiro OAuth+IDE-only. provider_bench digit check now normalizes
  Persian/Arabic digits (cf/mistral-small + cohere/command-a actually PASS).

## 2026-10-04 FINAL INTEGRATED — Iran-first policy + editorial bot
- MAX_POSTS_PER_DAY=500 / MAX_POSTS_PER_HOUR=60 (safety ceilings; edits
  never counted — created_at filter). Real controls stay editorial.
- Iran-first allocation (app/newsroom/iran_policy.py): soft ~90% target —
  P2/P3 stories defer one pass ONLY while Iran share < 70% AND Iran supply
  exists; capacity spills automatically otherwise. P0/P1 always pass.
- IRAN_CRISIS_MODE: auto-trigger on >=2 distinct-source P0 Iran events/30m,
  translation budget 6->12/pass, auto-exit after calm (60m). Verification
  NEVER weakens (priority is order, not trust).
- Multi-admin editorial intake (app/editorial/intake.py): long-poll getUpdates
  with persisted offset; numeric-user_id auth (bot_admins, migration 019);
  text/forward/photo/video/album/document submissions -> RawItem held
  (activation_ok=0) until an editor approves via preview buttons; then the
  SAME canonical pipeline (dedup->event->verification->story->publish).
  Forwards map known canonical identities; unknown origins never add
  independent confirmations. Media = Telegram file_id only, zero binaries.
  Feature flag EDITORIAL_BOT_INTAKE_ENABLED (deployed ON after healthy
  flag-off verification); owner bootstrapped from safe config (5504556066).
- Tests 370/370 (iran_policy 5 + editorial intake 10); governance PASS.

## 2026-10-04 24/7 full-source coverage + diversity (owner directive)
- Registry reconciled with rasteh_external_sources_iran_2026.xlsx: 78/78
  canonical entities already live; 106/171 endpoints URL-exact; all 67
  X/TruthSocial endpoints registered truthfully (X = LIMITED_X_ACCESS, no
  paid API; Truth Social RSS is Cloudflare-blocked server-side).
- Soft diversity scheduler (app/newsroom/diversity.py): canonical-identity
  rolling-hour caps (25% single / 45% top-two) defer ONLY dominant identities
  when alternative identities have publishable stories; P0 breaking weight
  and breaking-flagged sources always pass; deferral = retry next pass,
  nothing dropped or censored.
- Iran-first story priority (gates.priority_tier P0-P3) bumps job-queue ORDER
  only — verification trust, caps and dedupe untouched. Speed priority
  (NAYA/Yashar) never increases trust: single-source high-risk still HELD,
  low/medium single-source still publishes PROVISIONAL (verified live).
- Watchdog: SOURCE_MONOPOLY_DETECTED (>50% share + >=5 waiting identities)
  and SOURCE_STARVATION (>=5 fresh eligible items never linked to any event)
  — warn/diagnose only, never auto-block.
- Tests: tests/test_diversity.py (8) — same-identity-once, defer semantics,
  breaking exception, small-sample, order-not-trust, Iran-P0-beats-P3,
  metrics shape, monopoly+starvation detection.

## 2026-10-04 14:1xZ coverage follow-up (owner directives)
- MAX_POSTS_PER_DAY 120->240 (.env; hourly 30 stays as burst guard) — the
  trailing-24h window had genuinely filled with real posts and new sends
  dripped one-by-one; queue now flushes normally (11 SENTs in 12 min).
- Social policy (owner): publishing is TELEGRAM-ONLY. X account @rastehnews
  exists and is logged in, but X API posting was declined by owner (Pay-Per-Use
  cost risk); the auto-created X developer app has NO card attached, $0
  balance, posts nothing. Threads/Facebook dropped.

## Pipeline hardening (2026-10-04 overnight, `a406f41`)
- Translation thrash fix: 6 translations/pass budget + 5→60 min exponential backoff
  (held events no longer re-translate every ~3 min pass and starve the free tier).

## Sources
- 110 endpoints / 78 canonical identities (+ NAYA/Yashar telegram): every ACTIVE
  source delivered items in 24h (zero24 = 0); publications flow across many sources
  (no single-source lock). OSINT feeds store-only for stale backfill by design.

## Standing blockers → docs/OWNER-ACTION-REQUIRED.md
Telethon login · X email code (dialog parked) · Threads account decision ·
optional Mistral/Qwen phone-verify unlocks ·
optional Groq/OpenRouter key rotation (one-time local log echo)

## Isolation
Only akhbot-app / nine-router / Rasteh data touched; unrelated host services never modified.
