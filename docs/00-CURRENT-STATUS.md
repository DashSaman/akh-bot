# 00-CURRENT-STATUS — RUNTIME TRUTH (snapshot 2026-10-03 16:48Z, PART 4 COMPLETE)

- **Repository HEAD:** 8d5389f + docs commit (docs may run ahead — valid)
- **Production runtime SHA:** **8d5389f** (verified in-container; V2 engine live)
- **PART:** 1 = PASS · PART 2 = BLOCKED_EXTERNAL · PART 3 = PASS (V2 LIVE) · **PART 4 = PASS — verification lifecycle LIVE**
- **EVENT_ENGINE_V2_ENABLED:** true (cutover 2026-10-03T14:58Z)

## Runtime snapshot @16:48Z (read-only queries)
- SENT: **208** (V2 cutover baseline 202; duplicate-SEND violations **0**)
- Stories 1143 · Events 1382 · Claims 2261 · RawItems 1789
- **evidence_links: 2** (SUPPORTS + live CONTRADICTS) · **verification_runs: 356** — NEW_EVIDENCE 1 · SCHEDULED_REVERIFY 351 · DEADLINE 3 · **CONTRADICTION 1 (live)**
- Live contradiction case: ev 1377 / claim 2261 («شن الطيران… 60 غارة») → CONFLICTING + CONTRADICTS link + traced run; NO fabricated resolution
- Claims with next_verify_at / verification_attempts: 2 (bookkeeping live)
- schema_version: **14** (014 evidence_links + verification_runs + claim verify columns)

## PART-4 deliverables (live)
- **CORE-007 EvidenceLink**: SUPPORTS/CONTRADICTS/CONTEXT, provenance preserved (raw_item/source/lineage refs only — no RawItem duplication); UNIQUE(claim,item,relation) idempotent
- **CORE-008 VerificationRun**: triggers NEW_EVIDENCE/SCHEDULED_REVERIFY/CONTRADICTION/DEADLINE/MANUAL (all deterministic, 0 AI); dedupe_key = one run per scheduled attempt; next_verify_at maintained
- Independent origins = COLLAPSED origins: forward/repost lineage + registry identity (CENTCOM EN+AR=1, Trump X+TS=1); OFFICIAL origins authoritative for attribution only
- High-risk single-origin stays SINGLE_SOURCE (never CONFIRMED) — regression-tested + live
- Admin trace view live: /admin/verification/{event_id} (claims, supporting/contradicting evidence, origins, schedule, run history — auth-gated, no secrets)

## INGEST-002 hardening (found during Part-4 live acceptance)
- **REG-041 FIXED**: telegram_web watermark advanced past unpersisted messages (burst > 20/pass would permanently skip) → persist-then-advance + oldest-first pending-above-watermark + regression test (25-msg burst → 25 stored)
- Live audit: checkpoint-gap ids proved to be **id-holes (deleted posts), NOT lost data** — one-shot backfill found zero missing public posts
- Watermarks re-synced to checkpoint and re-advanced by the fixed collector

## V2 live behavior (carryover, unchanged)
- Persian posts with exact brand footer + «منبع: …» attribution; Arabic → HELD (no translator); fragments/low-value → HELD; EDIT-only invariant enforced (0 duplicate sends)

## Host isolation @8d5389f deploy
- Only akhbot-app replaced · other containers untouched · Apache/network/firewall untouched · no daemon restart/prune/reboot · backups before each migration (latest akhbot-20261003T160452Z.db)

## Blockers (external)
- Telethon session · free-AI key · Meta OAuth · public domain
