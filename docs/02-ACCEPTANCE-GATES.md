# 02-ACCEPTANCE-GATES
هر گیت: ورودی/خروجی/حالت شکست/نقطهٔ اجرای قانونی/تست‌های رگرسیون الزامی. GATE-15 **fail-closed** بلافاصله قبل از هر فراخوانی API بیرونی است.

| Gate | Input → Output | Failure state | Enforcement point | Required regression tests |
|---|---|---|---|---|
| GATE-01 SOURCE_ALLOWED | raw item origin → allow/pass | ITEM_REJECTED_SOURCE | `SourcesRepo.due()` + jobs-runner execution check | test_source_control (disabled job cancelled) |
| GATE-02 ITEM_FRESHNESS | story age vs policy → publish/skip | STALE_SUPERSEDED | jobs runner freshness gate | test_publisher stale |
| GATE-03 CLAIM_COMPLETENESS | claim WHO+WHAT(+WHERE/WHEN) → complete? | CLAIM_INCOMPLETE (speaker-prefix fail) | **MISSING — Part 3** | new: test_claim_completeness |
| GATE-04 ITEM_DEDUP | fingerprints → new/dup | DUPLICATE | clustering/dedup.py | test_dedup |
| GATE-05 EVENT_MATCH | item ↔ event similarity+burst → attach/create | NEW_EVENT vs ATTACH | **PARTIAL — near-dup only; Part 3** | new: test_event_burst_merge |
| GATE-06 CLAIM_DEDUP | claim ↔ existing claims (paraphrase) → merge | DUPLICATE_CLAIM | **MISSING — Part 3** | new: test_claim_paraphrase_dedup |
| GATE-07 VERIFICATION_POLICY | claims+lineage → state | SINGLE_SOURCE/CONFLICTING/HELD | verification/gates.py + pipeline | test_pipeline held cases |
| GATE-08 LANGUAGE_FA | story content (footer-stripped) → fa? | BLOCKED_LANGUAGE_GATE / NEEDS_LANGUAGE_PROCESSING | telegram_bot.story_content_language_check | test_language_gate (footer-fool case) |
| GATE-09 HEADLINE_QUALITY | headline → meaningful? | CONTENT_QUALITY_HOLD | gates.is_valid_headline + speaker parse | test_dedup rejects «ترامپ:» |
| GATE-10 BODY_QUALITY | headline vs body → ok/compact/fragment | PUBLIC_BODY_QUALITY_GATE | telegram_bot.body_quality_gate | test suite compact/fragment |
| GATE-11 SOURCE_ATTRIBUTION | known sources → one منبع line | SOURCE_NAME_RESOLUTION_ERROR | pipeline.source_display_names + render | new: test_source_line_once (Part 1) |
| GATE-12 PUBLICATION_IMPORTANCE | topic weight → above floor? | LOW_PUBLICATION_VALUE | classify_priority floor (pipeline) | tests exist; tune in Part 3 |
| GATE-13 MEDIA_RIGHTS | media policy → reuse/card/hold | MEDIA_NOT_ACCESSIBLE / BRANDED_FALLBACK | media.py rights default UNKNOWN | test_media card path |
| GATE-14 PLATFORM_POLICY | platform enabled+cost+auth → fan-out list | BLOCKED_BY_COST_POLICY / AUTH_REQUIRED / PAUSED | fanout.distribution_plan + platforms page | test_media platform states |
| GATE-15 FINAL_PUBLIC_PAYLOAD | rendered public text/caption → Persian+format valid? | **FAIL-CLOSED: zero API call** | telegram_bot send_message/edit_message/send_media gates | test_publisher + live Arabic fixture |

تست رگرسیون الزامی برای هر گیتِ علامت‌خورده در زمان پیاده‌سازی همان Part اضافه می‌شود (قاعدهٔ INV-025).
