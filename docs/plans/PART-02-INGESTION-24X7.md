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
## Exit (corrected semantics — PART-2 spec §0/§39)
- IF owner Telethon session available AND live acceptance passes: INGEST-003 = DONE, PART 2 = PASS.
- IF session absent (current state): all non-credential work (T1/T3, T2 mock-tested) DONE + deployed; INGEST-003 = **BLOCKED_EXTERNAL**; **PART 2 = BLOCKED_EXTERNAL** (not FAIL, not PASS).
- WEB_FALLBACK never downgraded (Tier-1 = 30s, sweep ≤120s, REG-002 pagination preserved).
