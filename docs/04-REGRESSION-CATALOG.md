# 04-REGRESSION-CATALOG
هر رگرسیونِ مشاهده‌شده در تولید → تست دائمی (INV-025). وضعیت: FIXED+TESTED (تست رگرسیون سبز) / OBSERVED (فعال/بی‌تست) / RISK (ممکن، بدون تست).

| ID | Symptom | Root cause | Invariant | Required test | Status @9affb54 |
|---|---|---|---|---|---|
| REG-001 | News sent to bot private chat | env line-glue → publish target fell back to private | INV-004/022 | dest type=channel validation | FIXED+TESTED |
| REG-002 | t.me/s >20 msgs lost | single-page fetch | INV (no lost news) | pagination watermark + overlap fetch_window (test_checkpoints) | FIXED+TESTED (@69059ab live: ck==wm, 0 dup keys) |
| REG-003 | HELD events starved | status filter excluded HELD | INV-009 | reverify includes HELD | FIXED+TESTED |
| REG-004 | Existing-story skipped on new evidence | `if story: continue` | INV-012 | existing-story update test | FIXED+TESTED |
| REG-005 | Stale FIFO backlog blocked breaking | no priority/freshness | INV (breaking first) | priority + STALE tests | FIXED+TESTED |
| REG-006 | Disabled-source queued job leaked | enqueue-time-only checks | INV-005 | execution-time cancel test | FIXED+TESTED |
| REG-007 | First line as headline | title=text.split | INV-011 | extract_headline tests | FIXED+TESTED |
| REG-008 | Speaker-only headline «ترامپ:» | no speaker regex | INV-011 | gates tests | FIXED+TESTED |
| REG-009 | literal split("chr(10)) | parsing formatted text | INV-003 | structured-fields tests | FIXED+TESTED |
| REG-010 | headline==body duplication | body from formatted blob | INV-014 | body_quality_gate tests | FIXED+TESTED |
| REG-011 | one-word/truncated body «این» | no body gate | INV-014 | fragment tests | FIXED+TESTED |
| REG-012 | raw `**` visible | no parse_mode/escape | EDIT spec | to_telegram_html tests | FIXED+TESTED |
| REG-013 | «✅ تأیید شد» clutter | old template | INV-013 | STATUS_ICONS test | FIXED+TESTED |
| REG-014 | robotic boilerplate | generation strings | EDIT spec | strip+gen tests | FIXED+TESTED |
| REG-015 | missing منبع | names not passed to formatter | INV-015 | source_display_names test | FIXED+TESTED |
| REG-016 | external URL/handle leak | no sanitizer | INV-016 | sanitize tests | FIXED+TESTED |
| REG-017 | raw Arabic published | gate on pre-strip text | INV-007/008 | content-level gate tests | FIXED+TESTED (live foreign=0) |
| REG-018 | Persian footer fooled detector | full-string check | INV-007 | footer-fool adversarial test | FIXED+TESTED |
| REG-019 | existing-story update bypassed translation | update path lacked lang gate | INV-008 | existing-path foreign test | FIXED+TESTED |
| REG-020 | legacy foreign queue payload sent | no send-time validation | INV-004 | pending purge + gate | FIXED+TESTED |
| REG-021 | media caption bypass | caption unchecked | INV-004 | send_media gate test | FIXED+TESTED |
| REG-022 | duplicate old class shadowed fix | file surgery leftovers | INV-024 | tests/test_no_duplicate_defs.py (caught live dup persian_ratio) | FIXED+TESTED |
| REG-023 | priority read as trust | conflated flags | INV-006 | separate-flags test | FIXED+TESTED |
| REG-024 | allowlist not revalidated at execution | enqueue-only | INV-005 | execution recheck test | FIXED+TESTED |
| REG-025 | branded card confused with original media | status labels | INV-024 | media-state labels (Part 6, CORE-006) | PARTIAL |
| REG-026 | docs/runtime mismatch | stale docs / unverified claims; PART-2 sync reverted PART-1.1 evidence (CORE-002 blocker text) + stale Production SHA | INV-023/024 | tests/test_governance_regressions.py (7 fixtures: generic PART-PASS any part, BLOCKED_EXTERNAL semantics, SHA two-field rule, ambiguous-metric rejection, stale-blocker-on-DONE) | FIXED+TESTED (REGRESSED during PART-2 sync → reclosed @PART-2.1 with the exact regression fixture) |
| REG-027 | PASS from tests w/o live evidence | reporting discipline | INV-023/024 | matrix runtime column | PARTIAL (matrix now enforces) |
| REG-028 | micro-post flood → story-per-post | title-keyed clustering | INV-013 | 6-fragment fixture (test_story_evolution) + shadow 218→50 stories | FIXED+LIVE (V2: 1 event/1 story per interview; live 2 stories from ~180 items in 36min) |
| REG-029 | interview multi-post split | no continuation | §6 context types | context TTL inheritance tests | FIXED+LIVE (context/burst tables active in V2 path) |
| REG-030 | source emoji/markup leaks | copy from source | EDIT spec | sanitizer emoji test | FIXED (emoji stripped in gate path) |
| REG-031 | incomplete speaker prefix published | no completeness gate | INV-011/GATE-03 | prefix→0 publication tests + live: 0 fragment posts since cutover | FIXED+LIVE |
| REG-032 | router exists, runtime never calls it | wiring partial | INV-017 | router-used test | PARTIAL (wired via settings._ai_router; no keys to prove live) → Part 5 |
| REG-033 | runtime depends on agent | — | INV-021 | soak evidence | FIXED+TESTED (24/7 in-container) |
| REG-034 | low-value crowds breaking | floor missing/loose | GATE-12 | floor tuning test | PARTIAL (floor=20 exists; observe) → Part 3 |
| REG-035 | media cache threatens disk | no TTL/cap | INV-020 | cleanup/TTL tests | FIXED+TESTED |
| REG-036 | new claim → new post instead of edit | edit not wired to merge flow | INV-012 | test_story_evolution EDIT-invariant + SEND_FORBIDDEN guard | FIXED+LIVE (runner guard live; duplicate-SEND violations 0; first natural EDIT pending) |
| REG-037 | burst messages fail to aggregate | no window config | EVENT spec keys | tests/test_burst.py (16) | FIXED+LIVE (EVENT_BURST_WINDOW_SECONDS active in V2) |
| REG-038 | same claim paraphrase → multiple stories | Jaccard-only dedup | INV-014 | tests/test_claim_dedup.py + cross-event fp-exact guard + shadow | FIXED+LIVE (shadow 24h paraphrase dup 0) |
| REG-039 | quote fragment without context | no completeness | GATE-03 | tests/test_source_context.py (12) | FIXED+LIVE (per-source TTL context in V2 path) |
| REG-040 | event identity changes with wording | title-keyed clustering | EVENT_IDENTITY | stable-identity tests + live distinct-event sample | FIXED+LIVE |
| REG-041 | watermark advances past unpersisted messages (burst > insert-limit permanently skipped) | fetch-then-advance order bug (telegram_web) | INGEST-002 persist-then-advance | tests/test_telegram_web.py burst fixture (25 msgs → 25 stored, wm=max persisted) | FIXED+TESTED live @8d5389f; audit of live gap ids proved NO data lost (id-holes = deleted posts) |
