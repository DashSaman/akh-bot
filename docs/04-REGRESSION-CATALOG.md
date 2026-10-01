# 04-REGRESSION-CATALOG
هر رگرسیونِ مشاهده‌شده در تولید → تست دائمی (INV-025). وضعیت: FIXED+TESTED (تست رگرسیون سبز) / OBSERVED (فعال/بی‌تست) / RISK (ممکن، بدون تست).

| ID | Symptom | Root cause | Invariant | Required test | Status @9affb54 |
|---|---|---|---|---|---|
| REG-001 | News sent to bot private chat | env line-glue → publish target fell back to private | INV-004/022 | dest type=channel validation | FIXED+TESTED |
| REG-002 | t.me/s >20 msgs lost | single-page fetch | INV (no lost news) | pagination watermark | FIXED+TESTED |
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
| REG-022 | duplicate old class shadowed fix | file surgery leftovers | INV-024 | single-definition import test | FIXED (import dedupe) — needs permanent test | RISK |
| REG-023 | priority read as trust | conflated flags | INV-006 | separate-flags test | FIXED+TESTED |
| REG-024 | allowlist not revalidated at execution | enqueue-only | INV-005 | execution recheck test | FIXED+TESTED |
| REG-025 | branded card confused with original media | status labels | INV-024 | media-state labels (Part 6, CORE-006) | PARTIAL |
| REG-026 | docs/runtime mismatch | stale docs | INV-024 | matrix sync | PARTIAL (this Part 0) |
| REG-027 | PASS from tests w/o live evidence | reporting discipline | INV-023/024 | matrix runtime column | PARTIAL (matrix now enforces) |
| REG-028 | same-event micro-post flood | every item → own event | INV-009/010 | burst-merge test | **OBSERVED (1020 events/2ch)** → Part 3 |
| REG-029 | one interview → multiple posts | no claim clustering | INV-009 | interview-fixture test | OBSERVED (Yashar/TIME) → Part 3 |
| REG-030 | source emoji/markup leaks | copy from source | EDIT spec | sanitizer emoji test | FIXED (emoji stripped in gate path) |
| REG-031 | incomplete speaker prefix published | no completeness gate | INV-011/GATE-03 | WHO+WHAT test | **OBSERVED** («ترامپ به مجله تایم:» pattern) → Part 3 |
| REG-032 | router exists, runtime never calls it | wiring partial | INV-017 | router-used test | PARTIAL (wired via settings._ai_router; no keys to prove live) → Part 5 |
| REG-033 | runtime depends on agent | — | INV-021 | soak evidence | FIXED+TESTED (24/7 in-container) |
| REG-034 | low-value crowds breaking | floor missing/loose | GATE-12 | floor tuning test | PARTIAL (floor=20 exists; observe) → Part 3 |
| REG-035 | media cache threatens disk | no TTL/cap | INV-020 | cleanup/TTL tests | FIXED+TESTED |
| REG-036 | new claim → new post instead of edit | edit not wired to merge flow | INV-012 | claim-merge→edit test | **OBSERVED** → Part 3 |
| REG-037 | burst messages fail to aggregate | no window config | EVENT spec keys | burst-window test | MISSING → Part 3 |
| REG-038 | same claim paraphrase → multiple stories | line-hash identity only | CLAIM dedup | paraphrase test | OBSERVED → Part 3 |
| REG-039 | quote fragment without context | no completeness | GATE-03 | quote-context test | OBSERVED → Part 3 |
| REG-040 | event identity changes with wording | title-keyed clustering | EVENT_IDENTITY | stable-identity test | OBSERVED → Part 3 |
