# 00-CURRENT-STATUS — RUNTIME TRUTH (snapshot 2026-10-01 15:45Z, PART 2.1)

- **Repository HEAD:** abfcf9d (docs/governance commits may run ahead of runtime — valid)
- **Production runtime SHA:** abfcf9d (P3-B deployed; verified in-container)
- **PART:** 1 = PASS · PART 2 = BLOCKED_EXTERNAL · **PART 3 = IN PROGRESS — P3-A ✅, P3-B ✅ (matcher, V2 off), P3-C next**
- **EVENT_ENGINE_V2_ENABLED:** false (P3-A deployed inactive; old pipeline authoritative)

## Runtime snapshot @2026-10-01 15:45Z (single read-only query set)
- Publication ledger SENT: **92**
- Jobs DONE: **159**
- Telegram remote-mapped publications: **89**
- HELD events: **68** (verification/quality gates — intentional)
- Queue pending: **0** · Queue failed (HISTORICAL contained backlog): 879
- Stories total: 1030

## Sources / collectors
- Allowlist ON: 1=naya_foriraq 2=withyashar (OWNER_ENABLED/AUTO/30s)؛ others OWNER_DISABLED
- Collector mode: Telegram=WEB_FALLBACK (TELETHON_AUTH_REQUIRED; listener deployed+mock-proven, inactive w/o session)
- Checkpoints (monotonic, restart-surviving): naya ck=wm=92254 · yashar ck=wm=24680 · SLA breach keys=[] (healthy)

## Workers / platform / admin / AI
- Heartbeats fresh: ingest/pipeline/reverify/jobs/watchdog/soak (<3min) · restart recovery proven
- Platforms: Telegram LIVE (@RastehNews) · X=BLOCKED_BY_COST_POLICY · IG/Threads=AUTH_REQUIRED · FB=NOT_CONFIGURED · Web=PREVIEW
- Admin: https://rasteh.softarg.ir dual-auth healthy · media cache 0MB
- AI: 0 providers → DETERMINISTIC; foreign content → HELD (no leak)

## Known BROKEN (Part 3 scope)
- EVENT-001 micro-post flood (1030 stories/2ch) + CLAIM-002/003, EVENT-003 missing

## Blockers (external)
- Telethon session · free-AI key · Meta OAuth · public domain
