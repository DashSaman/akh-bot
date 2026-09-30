# Testing

Run: `python -m pytest tests -q` (52 tests, all passing as of 2026-09-30).

| File | Covers |
|---|---|
| test_health.py | /health, /ready config states, migration idempotency |
| test_auth.py | login flow, wrong password, 429 throttle, logout, all admin pages render |
| test_sources.py | CRUD, APPROVED/DISCOVERED/BLOCKED, activation anchor, **backfill protection (old items never publish-eligible)** |
| test_dedup.py | all 4 stages: canonical URL (tracking-param collapse), content hash, Arabic↔Persian title normalization, SimHash; non-dup for different stories |
| test_rss.py | fetch+store, re-fetch idempotent, **invalid XML → error recorded + health decay**, HTTP 304 skip, timeout isolation |
| test_telegram_ingest.py | store/duplicate, **edits create revisions (originals preserved)**, pre-activation archive STORE_ONLY, forward lineage |
| test_pipeline.py | **dependency test (5 copies → 1 independent origin)**, **conflicting casualties → HELD (never confirmed headline)**, 2 independent origins corroborate, one master story per event, **LLM outage → events wait, no fake success** |
| test_writer.py | auditor keeps supported paragraphs, drops unsupported numbers (Persian digits!), drops ref-less paragraphs, JSON extraction robustness, GLM timeout/malformed handling, **LLM cache hit avoids second call**, prompt-injection delimitation |
| test_publisher.py | telegram text builder, **publish once + idempotent retry (no duplicate)**, failure → ledger FAILED → job backoff → success, dedupe_key drop, **pause blocks (all + per-platform) without failure**, stuck jobs requeued after restart, rate caps |
| test_seo.py | full quality gate incl. single H1/canonical/single JSON-LD/Organization publisher/dates, story sections, sitemaps, news sitemap, robots, **preview noindex vs live index**, RSS |
| test_backup.py | online SQLite backup round-trip (restore contains exactly pre-backup state) |

High-risk behavioral tests required by the spec (§118–122) are covered above:
duplicate raw item, duplicate event, edited item, invalid XML, HTTP timeout, GLM
timeout/malformed JSON, unsupported factual sentence, contradictory evidence,
duplicate publication, retry idempotency, platform failure isolation, restart
idempotency, kill switch, rate limiting, backup/restore, schema/sitemap/noindex,
admin auth.
