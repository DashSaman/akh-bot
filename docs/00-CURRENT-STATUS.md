# 00-CURRENT-STATUS — RUNTIME TRUTH (snapshot 2026-10-03 12:40Z, PART 3-D)

- **Repository HEAD:** 2d2851f (feat P3-D; docs commits may run ahead of runtime — valid)
- **Production runtime SHA:** 2d2851f (P3-D deployed; verified in-container AKHBOT_GIT_SHA)
- **PART:** 1 = PASS · PART 2 = BLOCKED_EXTERNAL · **PART 3 = IN PROGRESS — P3-A ✅, P3-B ✅, P3-C ✅, P3-D ✅ (source-context + burst, dormant behind V2=false), P3-E next**
- **EVENT_ENGINE_V2_ENABLED:** false (P3-A..P3-D modules deployed inactive; current public pipeline remains authoritative)

## Runtime snapshot @2026-10-03 12:40Z (single read-only query set)
- Publication ledger SENT: **197** (telegram remote-mapped 197; unchanged across the P3-D deploy — 0 unexpected publications)
- Jobs: done **264** · failed 881 (HISTORICAL contained backlog) · pending **0**
- Stories total: 1135 · Events HELD: 220 (verification/quality gates — intentional)
- Ingestion flow: **66 raw items in last 15 min** · orphan NEW items: **0**
- schema_version: **12** (migration 012 source_context/burst tables; additive, drill-proven)

## Sources / collectors
- Allowlist ON: 1=naya_foriraq 2=withyashar (OWNER_ENABLED, health 1.0, last_check 12:39:56Z)؛ others OWNER_DISABLED
- Collector mode: Telegram=WEB_FALLBACK (TELETHON_AUTH_REQUIRED; listener deployed+mock-proven, inactive w/o session)
- Checkpoints (persisted): naya last_remote_id=92254 (fetch_state wm 92423) · yashar last_remote_id=24680 (fetch_state wm 24838) · SLA breach keys=[] (healthy)

## P3-D additions (dormant until P3-E wiring)
- Migration 012: `source_context` / `burst_groups` / `burst_members` created empty (0 rows — no backfill, no historical regroup)
- Config: SOURCE_CONTEXT_TTL_SECONDS=1800 · EVENT_BURST_WINDOW_SECONDS=180 (env-tunable)
- REG-037/REG-039: IMPLEMENTED+TESTED / NOT_LIVE_YET (28 new tests; prefix-alone still 0 claim/event/story/pub — REG-031 guarded)

## Workers / platform / admin / AI
- Heartbeats fresh: ingest/pipeline/reverify/watchdog (<3min) · restart recovery proven
  (`jobs_last_run` is watchdog-watched but never written — pre-existing quirk, unchanged)
- Platforms: Telegram LIVE (@RastehNews) · X=BLOCKED_BY_COST_POLICY · IG/Threads=AUTH_REQUIRED · FB=NOT_CONFIGURED · Web=PREVIEW
- Admin: https://rasteh.softarg.ir dual-auth healthy · media cache 0MB
- AI: 0 providers → DETERMINISTIC; foreign content → HELD (no leak)

## Host isolation @deploy 2d2851f
- Only `akhbot-app` replaced · other containers (pv-reseller-dashboard, sentinelx-worker) untouched, up 2 days
- Apache untouched (local 200) · no daemon restart, no prune, no reboot · DB backup taken pre-deploy (akhbot-20261003T122949Z.db)

## Known BROKEN (Part 3 scope)
- EVENT-002 SEND/EDIT invariant + REG-028/036 wiring → P3-E (next); materiality/importance floor → P3-F

## Blockers (external)
- Telethon session · free-AI key · Meta OAuth · public domain
