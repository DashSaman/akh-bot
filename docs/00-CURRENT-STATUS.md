# 00-CURRENT-STATUS — RUNTIME TRUTH (snapshot 2026-10-04 11:0xZ, media-closeout)

- **Repository HEAD:** b5b7b29 (GitHub main synced; server clean)
- **Production runtime SHA:** cf3ff5a → media-closeout deploy this session
- **PART:** 1=PASS · 2=BLOCKED_EXTERNAL · 3=PASS (V2 LIVE) · 4=PASS · 5=PASS (9Router LIVE) · 6/7/8/9/10 = executable work COMPLETE
- **Governance:** PASS — Matrix 59 DONE / 0 PARTIAL / 0 MISSING / 0 BROKEN / 2 BLOCKED_EXTERNAL

## Runtime snapshot
- Publication ledger SENT: **322** (telegram remote-mapped; duplicate-SEND violations 0)

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
