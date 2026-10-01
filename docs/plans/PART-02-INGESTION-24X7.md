# PART-02 — INGESTION 24X7 (plan)

Goal: close the only ingestion gap (Telethon realtime) and formalize checkpoints.

## Tasks
1. **T1 checkpoint schema** — migrations/008: sources.last_remote_id/last_remote_ts/last_processed_item (+backfill from fetch_state watermarks). Test: test_portability extends — restart resume from checkpoint; overlap window (SOURCE_OVERLAP_SECONDS) fetches no duplicates.
2. **T2 Telethon listener (BLOCKED_EXTERNAL until owner session)**
   - Files: app/ingestion/telethon_listener.py: persistent client, `events.NewMessage(chats=monitored_map)`, dynamic map refresh from DB every 60s (no restart), edited/deleted reconciliation; immediate pipeline trigger on insert.
   - Tests (mock client): NewMessage→item<5s logic; map refresh; edit→revision; delete→marker.
   - Runtime: only after owner provides TELEGRAM_INGEST_* — acceptance: fresh channel post → raw_item within 5s (log evidence), WEB_FALLBACK stays as automatic fallback.
   - Commit boundary: schema+mock first (deployable now), live enable in separate commit.
3. **T3 source-SLA enforcement** — watchdog marks SOURCE_SLA_BREACH + forced immediate reconcile; admin Sources header shows «منابع عقب‌افتاده». Test: injected stale source triggers marker.
## Exit
INGEST matrix rows DONE (003 stays BLOCKED_EXTERNAL with mock DONE); lag=0 sustained; REG-002 class tests green.
