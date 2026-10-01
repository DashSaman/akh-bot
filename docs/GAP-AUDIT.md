# GAP-AUDIT — evidence-based (2026-10-01, post language-gate deploy)

Rule applied: DONE only with code/test/runtime proof from THIS session.

| Requirement | Status | Evidence |
|---|---|---|
| Realtime Telegram (Telethon NewMessage) | **BLOCKED_EXTERNAL** | Code exists (`telegram_ingest.py`, lazy); no owner session → runtime shows `WEB_FALLBACK` truthfully. Tier-1 poll 60s. |
| Web-fallback watermark pagination (no >20 loss) | DONE | `telegram_web.py` ?before= pages; live: 159 items/10min, lag=0 all 3 Tier-1 |
| Dedicated reverification_loop (≤300s) | DONE (this pass) | `scheduler.reverification_loop` + lifespan task; writes `reverify_last_run` |
| 60-minute resolution (UNVERIFIED_EXPIRED) | DONE | `pipeline._resolve_deadlines` (ARCHIVED+note; wording ⚠️) |
| Dedicated watchdog_loop | DONE (this pass) | heartbeat staleness alerts + orphan backlog marker, 120s |
| Orphan requeue (>120s) | PARTIAL | detection+marker now; auto-force requeue pending (pipeline pass covers in practice — orphans=0 live) |
| Item disposition/ignore-reason | PARTIAL | DUPLICATE/POLICY_HELD/CONTENT_QUALITY_HOLD/NEEDS_LANGUAGE_PROCESSING recorded via event states; per-item table not yet |
| Persian-only language gate | DONE | `is_persian_public_text` before every publish path; foreign public posts=0 live |
| Telegram HTML formatter (no raw **) | DONE | `to_telegram_html` + parse_mode=HTML; tests |
| Clean confirmed posts (no ✅ clutter) | DONE | STATUS_ICONS CONFIRMED=""; tests |
| Provisional→confirmed same-message edit | DONE | ledger edit path; live-proven (msg 109→109) |
| Headline quality gate | DONE | speaker-label regex + MIN_HEADLINE_INFORMATION; live 0 bad |
| Topic priority (fa/ar/en incl. Arabic war) | DONE | `classify_priority`; ar-war=100 tested |
| Priority ≠ verification trust | DONE | separate flags + tests (source_policy) |
| Free AI provider router (Groq/Gemini/OR) | **MISSING** | only LLMProvider protocol + GLM adapter + Fake; router/AI admin page not built (no keys) |
| Deterministic no-AI core | DONE | live: 0 providers, 100s of events/stories processed |
| Source CRUD web panel | PARTIAL | add/status/toggle/trust exist; edit/archive/test/fetch-now/views missing |
| Bulk source import | MISSING | — |
| Source health UI (per-source stats) | PARTIAL | health/last_success/errors in list; items-5m/1h/24h views missing |
| Manual intake page (خبر ارسالی) | MISSING | — |
| Telegram admin inbox (user IDs) | MISSING | — |
| Media ingestion/photo/video publish | MISSING | media_cache table exists only |
| Media cleanup loop | PARTIAL | soak loop writes metrics; TTL/size cleanup not built |
| Media admin page | MISSING | — |
| X/IG/Threads/FB publishers | BLOCKED_EXTERNAL | fanout policy exists; adapters stubs (OAuth absent; X=BLOCKED_BY_COST_POLICY) |
| Platform admin page | MISSING | statuses shown on dashboard only |
| 24/7 health page (سلامت) | PARTIAL | doctor.sh + heartbeats in DB; admin page missing |
| Source alert stream page | MISSING | heartbeats/logs only |
| 24h soak in panel | PARTIAL | jsonl metrics + SOAK markers; panel view missing |
| Website SEO set | DONE | schema/sitemaps/RSS/robots/trust pages + regression tests (preview mode) |
| Analytics/Growth | MISSING | docs only |
| Portability export/import/fresh | DONE | seed.py, source-seed.example.yml, verify_instance.sh (12/12 PASS live), backup/restore, migration docs; DR round-trip tests |
| Instance portability (ledger/watermarks) | DONE | tests test_portability.py (83→89 suite) |

**CRITICAL GAPS REMAINING (Phase A): 1** — Telethon realtime (needs one-time owner session; WEB_FALLBACK is safe/truthful). All other Phase-A items DONE with runtime proof.

Next-by-impact queue: manual intake + Telegram admin inbox → source CRUD completion (edit/test/fetch-now) → free-AI router + AI admin → media pipeline.
