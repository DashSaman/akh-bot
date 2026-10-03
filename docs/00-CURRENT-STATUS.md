# 00-CURRENT-STATUS — RUNTIME TRUTH (snapshot 2026-10-03 15:34Z, PART 3 COMPLETE)

- **Repository HEAD:** ebb0589 + docs commit (docs may run ahead of runtime — valid)
- **Production runtime SHA:** ebb0589 (verified in-container AKHBOT_GIT_SHA)
- **PART:** 1 = PASS · PART 2 = BLOCKED_EXTERNAL · **PART 3 = PASS — V2 ENGINE LIVE**
- **EVENT_ENGINE_V2_ENABLED:** **true** (since 2026-10-03T14:58Z; kill-switch = flip to false + restart)

## Runtime snapshot @2026-10-03 15:34Z (read-only queries)
- SENT: **204** (baseline at V2 cutover 202; +2 V2 posts, 0 duplicates)
- Stories 1142 · Events 1379 · Claims 2257 · RawItems 1783 · HELD events 233 (gates intentional)
- Jobs: publish_send done=2 · publish_edit=0 (awaits first natural material update) · duplicate-SEND violations=0
- schema_version: **13** (012 context/burst + 013 materiality)

## V2 live evidence (first 36 minutes)
- Post 1 (story 1141/ev 1378): flydubai/Tehran — 🔴 Persian full headline + «منبع: یاشار» + exact brand footer, remote_id 376
- Post 2 (story 1142/ev 1379): Hormuz tankers — distinct real event (over-merge 0)
- Arabic NAYA items → HELD NEEDS_LANGUAGE_PROCESSING (0 foreign published; no translator by design)
- LOW_PUBLICATION_VALUE holds observed (ENTERTAINMENT) — importance floor live
- Context rows 0 / burst 3+3 — burst grouping live; solo-prefix messages held no context yet (natural traffic)

## Shadow gate (before activation) — PASS on live 24h replay
- 218 items → 127 events → 50 stories → 50 send intents (1/story) · dup SEND 0 · incomplete 0 · paraphrase dup 0 (policy-aware I4) · foreign 0 · replay idempotent
- Shadow-driven fixes: decide() crash on real data, I7 drain semantics, identity-label extraction («ترامپ: …»), Stage-C overlap ratio floor + jc≥0.30

## Sources / collectors
- Allowlist ON: 1=naya_foriraq 2=withyashar (OWNER_ENABLED, health 1.0) · others OWNER_DISABLED
- Telegram=WEB_FALLBACK (TELETHON_AUTH_REQUIRED) · checkpoints advancing

## Workers / platform / admin / AI
- Heartbeats fresh (ingest/pipeline/reverify/watchdog) · V2 pipeline log lines confirm live path
- Platforms: Telegram LIVE (@RastehNews) · X=BLOCKED_BY_COST_POLICY · IG/Threads=AUTH_REQUIRED · Web=PREVIEW
- AI: 0 providers → DETERMINISTIC (V2 needs no AI) · Arabic held until owner configures translation

## Host isolation @V2 cutover
- Only akhbot-app restarted · other containers untouched · Apache untouched · no daemon restart/prune/reboot
- Rollback path: EVENT_ENGINE_V2_ENABLED=false + redeploy (RawItems preserved — engine is read-then-append)

## Known follow-ups (not Part-3 blockers)
- First natural publish_edit pending (material update on a SENT story) — unit+shadow proven, runner guard live
- Headline truncation at 140 chars can cut mid-word (cosmetic)
- PUB-003 importance audit script (P3-F §27) not built; floor itself live

## Blockers (external)
- Telethon session · free-AI key · Meta OAuth · public domain
