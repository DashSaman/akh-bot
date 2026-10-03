# 00-CURRENT-STATUS — RUNTIME TRUTH (snapshot 2026-10-03 17:4xZ, PART 5 COMPLETE)

- **Repository HEAD:** 9b75fbc + docs commit (docs may run ahead — valid)
- **Production runtime SHA:** **9b75fbc** (verified in-container; V2 engine live)
- **PART:** 1 = PASS · PART 2 = BLOCKED_EXTERNAL · PART 3 = PASS (V2 LIVE) · PART 4 = PASS · **PART 5 = BLOCKED_EXTERNAL (all code/tests/admin LIVE; zero provider keys — live translation awaits owner's free key)**
- **EVENT_ENGINE_V2_ENABLED:** true

## PART-5 state (translation production-ready, fail-closed preserved)
- Router hardened: config resolved ONCE at construction (no os.environ reads in _call — AST-tested); per-provider state incl. NOT_CONFIGURED/RATE_LIMITED/DEGRADED; keys redacted from all errors/logs; failover A→B→…→None/HOLD; ZERO_COST_MODE=true + AI_FREE_ONLY=true
- Translator v2: source language AUTHORITATIVE (ar/en/he/tr/ru/… force translation); consistency audit (NUMBERS_INVENTED / NEGATION_REVERSED fa+en+ar+he / CERTAINTY_ESCALATED) → reject = HOLD; cache by content-hash + prompt version (failures never cached); thread-bridge for sync V2
- V2 wiring: foreign event → translate → consistency → SAME gates (verification/importance/attribution/language) — no bypass; failure → NEEDS_LANGUAGE_PROCESSING HELD
- /admin/ai LIVE: provider order/state/health/latency/calls + enable/disable/priority (persisted, live-applied) + test button; keys never displayed; anon → login redirect
- Live: all 5 providers NOT_CONFIGURED (truthful); NAYA Arabic → HELD (344 NEEDS_LANGUAGE_PROCESSING log lines in 6-min window); zero foreign leaks; owner adds any free key (GROQ_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY / …) in .env + redeploy → translation activates with NO code change

## Runtime snapshot (post-Part-5 deploy)
- SENT: **208** (stable; duplicate-SEND violations **0**) · verification_runs 514+ · heartbeats fresh (ingest 12s) · schema 14
- NAYA/Yashar healthy (watermark fix from Part-4 live; backfill audit: no data ever lost)

## Host isolation @9b75fbc deploy
- Only akhbot-app replaced · other containers untouched · Apache/network untouched · no daemon restart/prune/reboot

## Blockers (external)
- **free AI key (unblocks LANG-003 live + AI-002 live proof)** · Telethon session · Meta OAuth · public domain
