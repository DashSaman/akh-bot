# 01-REQUIREMENTS-MATRIX
Statuses: DONE / PARTIAL / BROKEN / MISSING / BLOCKED_EXTERNAL only. Evidence = real files/tests/runtime observed (audit 2026-10-01, prod SHA 9affb54). «—» = none found.

| ID | Requirement | Status | Code Evidence | Test Evidence | Runtime Evidence | Docs | Last SHA | Blocker/Notes | Part |
|---|---|---|---|---|---|---|---|---|---|
| CORE-001 | Canonical core entities exist (Source, RawItem, Claim, Event, Story, StoryVersion, PublicationJob/Ledger) | PARTIAL | app/db/migrations/001-005, app/db/repo.py | tests/test_pipeline.py | DB rows exist | DATA-MODEL.md | 9affb54 | boundaries leak via legacy draft blob | 1 |
| CORE-004 | StoryVersion model: one Story evolves many versions; editorial content only in structured fields | PARTIAL | StoriesRepo.set_lifecycle, story_versions table | test_autonomy update-in-place | versions live | DATA-MODEL.md | 9affb54 | legacy drafts still carry preformatted body blob | 1 |
| CORE-005 | Publication outbox/ledger model: job→ledger row→remote mapping; no re-publication on new RawItem | DONE | publications UNIQUE + jobs table + handler edit-path | test_publisher idempotency+edit | 86 SENT mapped; retry=0 dup | PUBLISHING.md | 9affb54 | — | — |
| CORE-006 | Canonical MediaAsset structural entity/state model (incl. truthful status labels) | PARTIAL | media_cache table | test_media (asset) | media rows | DATA-MODEL.md | 9affb54 | status labels missing (REG-025) | 6 |
| CORE-007 | EvidenceLink entity and canonical evidence relations | MISSING | — | — | — | DATA-MODEL.md | 97e98e2 | — | 4 |
| CORE-008 | VerificationRun entity and traceable verification history | MISSING | — | — | — | DATA-MODEL.md | 97e98e2 | — | 4 |
| CORE-009 | PlatformAccount entity and platform credential/account state model | MISSING | — | — | — | DATA-MODEL.md | 97e98e2 | — | 8 |
| CORE-002 | No RawItem → publisher direct path | PARTIAL | pipeline renders only via build_public_text | tests/test_language_gate.py | foreign=0 live | — | 9affb54 | direct-story admin path exists (scripts) without canonical Story render for all fields | 1 |
| CORE-003 | Public output only from canonical Story/StoryVersion | PARTIAL | StoriesRepo.create/set_lifecycle | tests/test_source_control.py | SENT 86 mapped | — | 9affb54 | some drafts still carry body blob, not pure structured fields | 1 |
| SRC-001 | Owner allowlist only (INV-005) | DONE | repo.due() OWNER_ENABLED filter; jobs runner execution-check | test_source_control.py::disabled… | naya=1/yashar=2 enabled, others DISABLED | SOURCES.md | 9affb54 | settings marker key empty (cosmetic) | — |
| SRC-002 | Priority=speed not trust (INV-006) | DONE | priority_rank in due() ORDER; verification_allowed separate | test_source_policy.py | DB flags separate | — | 9affb54 | — | — |
| SRC-003 | Full CRUD panel incl test/fetch-now/archive | PARTIAL | admin/views.py + platforms routes | test_auth pages | /admin/sources live | ADMIN-PANEL.md | 9affb54 | Edit UI limited; delete=archive only | 7 |
| SRC-004 | Publication policy per source | DONE | migration 007 + pipeline gate | test_source_control.py | AUTO set on both | — | 9affb54 | — | — |
| INGEST-001 | 2-min safety sweep, Tier-1 30s | DONE | polling_interval_seconds in due() | test_source_control.py::due_uses_seconds | last_fetch 13:49:57 fresh | OPERATIONS.md | 9affb54 | — | — |
| INGEST-002 | Watermark pagination (no >20 loss) | DONE | telegram_web.py ?before= pages | test_telegram_web.py | lag=0 both channels | — | 9affb54 | — | — |
| INGEST-003 | Telethon realtime NewMessage | BLOCKED_EXTERNAL | telegram_ingest.py handler scaffold | — | WEB_FALLBACK truthfully shown | — | 9affb54 | owner session absent (TELETHON_AUTH_REQUIRED) | 2 |
| INGEST-004 | Restart recovery of all workers | DONE | lifespan tasks + jobs requeue_running | test_jobs via suite | hb all fresh post-restart ×N | OPERATIONS | 9affb54 | — | — |
| CLAIM-001 | Atomic claim extraction | PARTIAL | gates/pipeline baseline + LLM path | test_pipeline.py | claims rows exist | VERIFICATION.md | 9affb54 | baseline= line-hash heuristic; no paraphrase dedup → REG-038 | 3 |
| CLAIM-002 | Claim completeness gate (WHO+WHAT) | MISSING | — (headline gate exists, not WHO/WHAT) | — | — | — | 9affb54 | GATE-CLAIM-COMPLETE absent → REG-031 | 3 |
| CLAIM-003 | Claim merge/dedup across messages | MISSING | — | — | 986 stories/1020 events prove flood | — | 9affb54 | REG-028/029/037/038 | 3 |
| EVENT-001 | One event per real-world occurrence (INV-009/010) | BROKEN | clustering only near-dup | test_dedup (dup only) | 1020 events ≈ items; interview → multiple posts | — | 9affb54 | REG-028/029/040 | 3 |
| EVENT-002 | Same-event update edits same message (INV-012) | PARTIAL | ledger edit path exists | test_breaking_flow | msg 109→109 proven once | — | 9affb54 | not wired to new-claim-for-event flow | 3 |
| EVENT-003 | Burst aggregation windows | MISSING | — (config keys absent) | — | — | — | 9affb54 | spec keys EVENT_BURST_* undefined | 3 |
| VERIFY-001 | Hard gates (high-risk single-source, conflict) | DONE | verification/gates.py | test_pipeline held cases | HELD=59 live | VERIFICATION.md | 9affb54 | — | — |
| VERIFY-002 | Independent-origin count (lineage) | DONE | lineage_key collapse | test_pipeline 5→1 | works | — | 9affb54 | — | — |
| VERIFY-003 | 5-min reverification incl HELD | DONE | reverification_loop ACTIVE_EVENT_STATUSES | test_autonomy.py | reverify hb fresh | — | 9affb54 | — | — |
| VERIFY-004 | 60-min resolution deadline | DONE | _resolve_deadlines | test suite | no stale VERIFYING live | — | 9affb54 | maps to ARCHIVED+note | — |
| LANG-001 | Persian-only public gate (INV-007/008) | DONE | story_content_language_check content-level | test_language_gate.py | public foreign=0/75 | — | 9affb54 | — | — |
| LANG-002 | Fail-closed at every publisher API | DONE | gates in send/edit/send_media | test_media/test_publisher | live Arabic fixture → 0 API calls | — | 9affb54 | — | — |
| LANG-003 | ar/en/he→fa translation before publish | BLOCKED_EXTERNAL | translator.py + FreeAiRouter | — | foreign→HELD (correct no-leak) | — | 9affb54 | zero provider keys → HOLD forever until key | 5 |
| EDIT-001 | Meaningful headline gate | DONE | is_valid_headline + speaker parse | test_dedup/gates | 0 bad headlines live | — | 9affb54 | — | — |
| EDIT-002 | Body quality gate (no dup/fragment) | DONE | body_quality_gate compact mode | test suite | sweeps show clean | — | 9affb54 | — | — |
| EDIT-003 | Icon-only lifecycle, no «✅ تأیید شد» | DONE | STATUS_ICONS | test_language_gate | channel clean | EDITORIAL-STYLE | 9affb54 | — | — |
| EDIT-004 | Source attribution exactly once, names only | DONE | build_public_text source_names | tests | منبع in samples | — | 9affb54 | — | — |
| MEDIA-001 | sendPhoto/sendVideo + Persian caption | DONE | telegram_bot.send_media | test_media.py | msg 247 photo live | — | 9affb54 | — | 6 |
| MEDIA-002 | Temp cache + cleanup + disk guard | DONE | media.py cleanup/publisher gates | test_media.py | cache=0 live | — | 9affb54 | — | 6 |
| MEDIA-003 | Source-media capture (original) | PARTIAL | metadata ref stored in WEB_FALLBACK | — | MEDIA_REFERENCE_ONLY state | — | 9affb54 | needs Telethon for bytes → REG-025 | 6 |
| MEDIA-004 | Branded fallback card | DONE | media.branded_card Pillow | test_media | card sent live | — | 9affb54 | — | 6 |
| MEDIA-005 | Media admin page | DONE | media_views.py | test_media page | /admin/media live | — | 9affb54 | — | 6 |
| PUB-001 | Idempotent ledger (no dup posts) | DONE | publications UNIQUE + handler edit-path | test_publisher | retry=0 dup proven | PUBLISHING.md | 9affb54 | — | — |
| PUB-002 | Priority queue + freshness gate | DONE | migration 004 + STALE_SUPERSEDED | test_publisher | backlog contained | — | 9affb54 | — | — |
| PUB-003 | Importance floor (no low-value flood) | PARTIAL | classify_priority LOW floor | test suite | some low-value still published historically | — | 9affb54 | floor=20; tuning needed | 3 |
| PLATFORM-001 | Telegram LIVE | DONE | telegram_bot.py | all pub tests | @RastehNews LIVE | — | 9affb54 | — | — |
| PLATFORM-002 | X/IG/Threads/FB adapters | BLOCKED_EXTERNAL | fanout.py placeholders | mock only | AUTH_REQUIRED/BLOCKED_BY_COST_POLICY truthful | — | 9affb54 | owner OAuth/keys | 8 |
| PLATFORM-003 | Platform control panel | DONE | platforms.py + template | test_media page tests | /admin/platforms live | — | 9affb54 | — | — |
| ADMIN-001 | Private dual-auth admin domain | DONE | deploy/apache vhost + htpasswd | — | rasteh.softarg.ir 401 anon | MIGRATION.md | 9affb54 | — | — |
| ADMIN-002 | AI admin page | MISSING | — | — | — | — | 9affb54 | Part 7 | 7 |
| ADMIN-003 | Manual news intake (web+inbox) | MISSING | — | — | — | — | 9affb54 | Part 7 | 7 |
| ADMIN-004 | Health/24-7 dashboard page | PARTIAL | doctor.sh + heartbeats in DB | — | doctor exit 0 | — | 9affb54 | full admin page missing | 7 |
| AI-001 | Optional, zero-cost router | PARTIAL | integrations/llm/router.py | — | 0 providers → deterministic | AI-USE-POLICY | 9affb54 | no keys configured | 5 |
| AI-002 | Provider failover A→B→C→det | PARTIAL | router loop | — | untested live (no keys) | — | 9affb54 | BLOCKED for live-proof | 5 |
| AI-003 | Factual consistency audit of AI output | PARTIAL | translator.consistent_with_source | unit only | — | — | 9affb54 | — | 5 |
| AUT-001 | 24/7 in-container workers, no agent | DONE | lifespan 6 tasks + restart unless-stopped | restart tests | soak metrics jsonl | AUTONOMY | 9affb54 | — | — |
| AUT-002 | Watchdog + orphan + SLA markers | DONE | watchdog_loop | test suite | hb fresh, orphan=0 | — | 9affb54 | — | — |
| WATCH-001 | Soak 24h metrics service-collected | DONE | soak_and_cleanup_loop | — | soak-metrics.jsonl growing | — | 9affb54 | — | — |
| SEC-001 | Persian HTML escaping, CSRF, throttle | DONE | to_telegram_html, CSRF on all admin POST | tests | live battery PASS | SECURITY.md | 9affb54 | — | — |
| PORT-001 | Instance portability (ledger/watermark/priority) | DONE | seed.py, verify_instance.sh | test_portability.py | verify 12/12 PASS | MIGRATION.md | 9affb54 | — | 9 |
| PORT-002 | DR round-trip | PARTIAL | backup/restore scripts | test_backup.py | restore drill = unit-level only (full prod drill pending) | — | 9affb54 | full prod drill pending | 9 |
| WEB-001 | Public site pages + trust pages | DONE | web/routes.py | test_seo.py | preview mode live | — | 9affb54 | domain undecided → PREVIEW | 10 |
| SEO-001 | Single schema graph, sitemaps, RSS, robots | DONE | seo/seo.py | test_seo.py | endpoints live | SEO-GEO-AEO | 9affb54 | — | 10 |
| GROWTH-001 | Analytics/UTM/Soak dashboard | MISSING | — | — | — | — | 9affb54 | Part 10 | 10 |

## Tallies (recomputed, evidence-rule enforced)
DONE 33 · PARTIAL 15 · BROKEN 1 · MISSING 9 · BLOCKED_EXTERNAL 3 — total 61
