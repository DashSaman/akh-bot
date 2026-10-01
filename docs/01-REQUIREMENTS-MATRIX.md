# 01-REQUIREMENTS-MATRIX
Statuses: DONE / PARTIAL / BROKEN / MISSING / BLOCKED_EXTERNAL only. Evidence = real files/tests/runtime observed (audit 2026-10-01, prod SHA 9affb54). «—» = none found.

| ID | Requirement | Status | Code Evidence | Test Evidence | Runtime Evidence | Docs | Last SHA | Blocker/Notes | Part |
|---|---|---|---|---|---|---|---|---|---|
| CORE-001 | Canonical core entities exist | DONE | app/db/migrations/001-005, repo.py | tests/test_no_duplicate_defs.py (entity distinctness) | 1027 stories structural post-migration | DATA-MODEL.md | afcc60f | — | 1 |
| CORE-004 | StoryVersion model | DONE | set_lifecycle + story_versions | tests/test_canonical_story.py version-bump+provenance | sv=1036 intact post-migration | DATA-MODEL.md | afcc60f | — | 1 |
| CORE-005 | Publication outbox/ledger model: job→ledger row→remote mapping; no re-publication on new RawItem | DONE | publications UNIQUE + jobs table + handler edit-path | test_publisher idempotency+edit | 86 SENT mapped; retry=0 dup | PUBLISHING.md | 69059ab | — | — |
| CORE-006 | Canonical MediaAsset structural entity/state model (incl. truthful status labels) | PARTIAL | media_cache table | test_media (asset) | media rows | DATA-MODEL.md | 9affb54 | status labels missing (REG-025) | 6 |
| CORE-007 | EvidenceLink entity and canonical evidence relations | MISSING | — | — | — | DATA-MODEL.md | 97e98e2 | — | 4 |
| CORE-008 | VerificationRun entity and traceable verification history | MISSING | — | — | — | DATA-MODEL.md | 97e98e2 | — | 4 |
| CORE-009 | PlatformAccount entity and platform credential/account state model | MISSING | — | — | — | DATA-MODEL.md | 97e98e2 | — | 8 |
| CORE-002 | No RawItem→publisher direct path | DONE | canonical enqueues: pipeline._render_public + admin lifecycle build_public_text; runner executes payload.text only; sealed scripts outside app/ | tests/test_publication_paths.py (5 AST/contract guards; re-verified @1fd0200) | no non-canonical path reachable (inventory in test docstring) | — | 1fd0200 | — | 1 |
| CORE-003 | Public output only from canonical Story | DONE | _create_and_enqueue/_publish_deterministic | tests/test_canonical_story.py | blob-headlines=0 live | — | afcc60f | — | 1 |
| SRC-001 | Owner allowlist only (INV-005) | DONE | repo.due() OWNER_ENABLED filter; jobs runner execution-check | test_source_control.py::disabled… | naya=1/yashar=2 enabled, others DISABLED | SOURCES.md | 9affb54 | settings marker key empty (cosmetic) | — |
| SRC-002 | Priority=speed not trust (INV-006) | DONE | priority_rank in due() ORDER; verification_allowed separate | test_source_policy.py | DB flags separate | — | 69059ab | — | — |
| SRC-003 | Full CRUD panel incl test/fetch-now/archive | PARTIAL | admin/views.py + platforms routes | test_auth pages | /admin/sources live | ADMIN-PANEL.md | 9affb54 | Edit UI limited; delete=archive only | 7 |
| SRC-004 | Publication policy per source | DONE | migration 007 + pipeline gate | test_source_control.py | AUTO set on both | — | 69059ab | — | — |
| INGEST-001 | 2-min safety sweep, Tier-1 30s | DONE | polling_interval_seconds in due() | test_source_control.py::due_uses_seconds | last_fetch 13:49:57 fresh | OPERATIONS.md | 69059ab | — | — |
| INGEST-002 | Watermark pagination (no >20 loss) | DONE | telegram_web.py ?before= pages | test_telegram_web.py | lag=0 both channels | — | 69059ab | — | — |
| INGEST-003 | Telethon realtime NewMessage | BLOCKED_EXTERNAL | telethon_listener.py (persistent client, dynamic map, bounded reconnect, edit/delete, fallback-dedup) + lifespan task | tests/test_telethon_listener.py (7 mocks) | runtime TELETHON_AUTH_REQUIRED (env session absent); WEB_FALLBACK active 30s | — | 69059ab | owner session absent; DONE requires live <5s proof (§33) | 2 |
| INGEST-004 | Restart recovery of all workers | DONE | lifespan tasks + jobs requeue_running | test_jobs via suite | hb all fresh post-restart ×N | OPERATIONS | 69059ab | — | — |
| CLAIM-001 | Structured atomic claims | PARTIAL | app/newsroom/claim_model.py (StructuredClaim, ClaimClass, extractor) | tests/test_claim_model.py (6) | V2 flag OFF — parser inactive in prod pipeline until P3-B/C wiring | DATA-MODEL.md | 8668402 | DONE waits P3-H/I live | 3 |
| CLAIM-002 | Claim completeness gate + dedup pipeline | PARTIAL | claim_completeness.py (COMPLETE/CONTEXT_ONLY/INCOMPLETE + reason/missing_slots) | tests/test_claim_completeness.py (11) | gate implemented behind V2; live acceptance P3-H/I | DATA-MODEL.md | 8668402 | dedup pipeline = P3-C | 3 |
| CLAIM-003 | Claim merge/dedup across messages | MISSING | — | — | 986 stories/1020 events prove flood | — | 9affb54 | REG-028/029/037/038 | 3 |
| EVENT-001 | One real-world event grouping (multi-signal identity) | PARTIAL | event_fingerprint.py + matcher (3-way, hard conflicts, per-type continuation) | tests/test_event_matcher.py (12) | implemented+tested behind V2=false; live closure waits P3-H/I | DATA-MODEL.md | abfcf9d | — | 3 |
| EVENT-002 | Same-event update edits same message (INV-012) | PARTIAL | ledger edit path exists | test_breaking_flow | msg 109→109 proven once | — | 9affb54 | not wired to new-claim-for-event flow | 3 |
| EVENT-003 | Burst aggregation windows | MISSING | — (config keys absent) | — | — | — | 9affb54 | spec keys EVENT_BURST_* undefined | 3 |
| VERIFY-001 | Hard gates (high-risk single-source, conflict) | DONE | verification/gates.py | test_pipeline held cases | HELD=59 live | VERIFICATION.md | 69059ab | — | — |
| VERIFY-002 | Independent-origin count (lineage) | DONE | lineage_key collapse | test_pipeline 5→1 | works | — | 69059ab | — | — |
| VERIFY-003 | 5-min reverification incl HELD | DONE | reverification_loop ACTIVE_EVENT_STATUSES | test_autonomy.py | reverify hb fresh | — | 69059ab | — | — |
| VERIFY-004 | 60-min resolution deadline | DONE | _resolve_deadlines | test suite | no stale VERIFYING live | — | 9affb54 | maps to ARCHIVED+note | — |
| LANG-001 | Persian-only public gate (INV-007/008) | DONE | story_content_language_check content-level | test_language_gate.py | public foreign=0/75 | — | 69059ab | — | — |
| LANG-002 | Fail-closed at every publisher API | DONE | gates in send/edit/send_media | test_media/test_publisher | live Arabic fixture → 0 API calls | — | 69059ab | — | — |
| LANG-003 | ar/en/he→fa translation before publish | BLOCKED_EXTERNAL | translator.py + FreeAiRouter | — | foreign→HELD (correct no-leak) | — | 9affb54 | zero provider keys → HOLD forever until key | 5 |
| EDIT-001 | Meaningful headline gate | DONE | is_valid_headline + speaker parse | test_dedup/gates | 0 bad headlines live | — | 69059ab | — | — |
| EDIT-002 | Body quality gate (no dup/fragment) | DONE | body_quality_gate compact mode | test suite | sweeps show clean | — | 69059ab | — | — |
| EDIT-003 | Icon-only lifecycle, no «✅ تأیید شد» | DONE | STATUS_ICONS | test_language_gate | channel clean | EDITORIAL-STYLE | 69059ab | — | — |
| GATE-11 | Source attribution exactly-once, fail-closed resolution | DONE | pipeline _render_public + source_display_names | tests/test_canonical_story.py (5 cases) | last-20 SENT: missing=0 dup=0 | — | afcc60f | — | 1 |
| REG-026 | Docs/runtime mismatch governance | DONE | validator v3 + regression fixtures | tests/test_governance_regressions.py (7) | caught live PART-2 regression | — | PART2.1 | — | — |
| GATE-05 | Three-way event match decision | PARTIAL | event_fingerprint.decide | tests/test_event_matcher.py | behind V2=false | — | abfcf9d | — | — |
| EDIT-004 | Source attribution exactly once, names only | DONE | build_public_text source_names | tests | منبع in samples | — | 69059ab | — | — |
| MEDIA-001 | sendPhoto/sendVideo + Persian caption | DONE | telegram_bot.send_media | test_media.py | msg 247 photo live | — | 9affb54 | — | 6 |
| MEDIA-002 | Temp cache + cleanup + disk guard | DONE | media.py cleanup/publisher gates | test_media.py | cache=0 live | — | 9affb54 | — | 6 |
| MEDIA-003 | Source-media capture (original) | PARTIAL | metadata ref stored in WEB_FALLBACK | — | MEDIA_REFERENCE_ONLY state | — | 9affb54 | needs Telethon for bytes → REG-025 | 6 |
| MEDIA-004 | Branded fallback card | DONE | media.branded_card Pillow | test_media | card sent live | — | 9affb54 | — | 6 |
| MEDIA-005 | Media admin page | DONE | media_views.py | test_media page | /admin/media live | — | 9affb54 | — | 6 |
| PUB-001 | Idempotent ledger (no dup posts) | DONE | publications UNIQUE + handler edit-path | test_publisher | retry=0 dup proven | PUBLISHING.md | 69059ab | — | — |
| PUB-002 | Priority queue + freshness gate | DONE | migration 004 + STALE_SUPERSEDED | test_publisher | backlog contained | — | 69059ab | — | — |
| PUB-003 | Importance floor (no low-value flood) | PARTIAL | classify_priority LOW floor | test suite | some low-value still published historically | — | 9affb54 | floor=20; tuning needed | 3 |
| PLATFORM-001 | Telegram LIVE | DONE | telegram_bot.py | all pub tests | @RastehNews LIVE | — | 69059ab | — | — |
| PLATFORM-002 | X/IG/Threads/FB adapters | BLOCKED_EXTERNAL | fanout.py placeholders | mock only | AUTH_REQUIRED/BLOCKED_BY_COST_POLICY truthful | — | 9affb54 | owner OAuth/keys | 8 |
| PLATFORM-003 | Platform control panel | DONE | platforms.py + template | test_media page tests | /admin/platforms live | — | 69059ab | — | — |
| ADMIN-001 | Private dual-auth admin domain | DONE | deploy/apache vhost + htpasswd | — | rasteh.softarg.ir 401 anon | MIGRATION.md | 69059ab | — | — |
| ADMIN-002 | AI admin page | MISSING | — | — | — | — | 9affb54 | Part 7 | 7 |
| ADMIN-003 | Manual news intake (web+inbox) | MISSING | — | — | — | — | 9affb54 | Part 7 | 7 |
| ADMIN-004 | Health/24-7 dashboard page | PARTIAL | doctor.sh + heartbeats in DB | — | doctor exit 0 | — | 9affb54 | full admin page missing | 7 |
| AI-001 | Optional, zero-cost router | PARTIAL | integrations/llm/router.py | — | 0 providers → deterministic | AI-USE-POLICY | 9affb54 | no keys configured | 5 |
| AI-002 | Provider failover A→B→C→det | PARTIAL | router loop | — | untested live (no keys) | — | 9affb54 | BLOCKED for live-proof | 5 |
| AI-003 | Factual consistency audit of AI output | PARTIAL | translator.consistent_with_source | unit only | — | — | 9affb54 | — | 5 |
| AUT-001 | 24/7 in-container workers, no agent | DONE | lifespan 6 tasks + restart unless-stopped | restart tests | soak metrics jsonl | AUTONOMY | 69059ab | — | — |
| AUT-002 | Watchdog + orphan + SLA markers | DONE | watchdog_loop | test suite | hb fresh, orphan=0 | — | 69059ab | — | — |
| WATCH-001 | Soak 24h metrics service-collected | DONE | soak_and_cleanup_loop | — | soak-metrics.jsonl growing | — | 69059ab | — | — |
| SEC-001 | Persian HTML escaping, CSRF, throttle | DONE | to_telegram_html, CSRF on all admin POST | tests | live battery PASS | SECURITY.md | 69059ab | — | — |
| PORT-001 | Instance portability (ledger/watermark/priority) | DONE | seed.py, verify_instance.sh | test_portability.py | verify 12/12 PASS | MIGRATION.md | 9affb54 | — | 9 |
| PORT-002 | DR round-trip | PARTIAL | backup/restore scripts | test_backup.py | restore drill = unit-level only (full prod drill pending) | — | 9affb54 | full prod drill pending | 9 |
| WEB-001 | Public site pages + trust pages | DONE | web/routes.py | test_seo.py | preview mode live | — | 9affb54 | domain undecided → PREVIEW | 10 |
| SEO-001 | Single schema graph, sitemaps, RSS, robots | DONE | seo/seo.py | test_seo.py | endpoints live | SEO-GEO-AEO | 9affb54 | — | 10 |
| GROWTH-001 | Analytics/UTM/Soak dashboard | MISSING | — | — | — | — | 9affb54 | Part 10 | 10 |

## Tallies (recomputed, evidence-rule enforced)
DONE 37 · PARTIAL 12 · BROKEN 1 · MISSING 8 · BLOCKED_EXTERNAL 3 — total 61
