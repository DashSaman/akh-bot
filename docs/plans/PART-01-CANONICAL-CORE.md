# PART-01 — CANONICAL CORE (plan, rev3 — final scope, single-phase)

Scope guard: structural news core ONLY. Explicitly OUT (later parts): media status-label work (Part 6), event matching / claim semantic dedup / burst aggregation (Part 3), verification-history entities (Part 4), platform-account entities (Part 8). The live Trump/TIME micro-post incident stays untouched here.

## Coverage map (each assigned Matrix ID → tasks → exit evidence; all completable inside Part 1)

| Matrix ID | Task(s) | Exit evidence (achievable in Part 1) |
|---|---|---|
| CORE-001 canonical entities exist | T1 | AST single-definition guard green; entity boundary test (Source/RawItem/Claim/Event/Story/StoryVersion/PublicationJob-Ledger constructible & distinct) |
| CORE-002 no RawItem→publisher direct path | T2 | test_canonical_story: public render built only from structured editorial fields |
| CORE-003 public output only from canonical Story | T2 | renderer contract test + 5 newest prod stories field-only (runtime sample) |
| CORE-004 StoryVersion model | T2 | fields: headline/lead/details + legitimate metadata (event_id, version, timestamps, language, topic, claim_refs, source_names); version-bump test |
| GATE-11 source attribution | T4 | test_source_line_once: known-source → exactly one «منبع:»; unresolvable → SOURCE_NAME_RESOLUTION_ERROR hold |
| REG-022 duplicate class shadows fix | T1 | permanent tests/test_no_duplicate_defs |
| REG-026 docs/runtime mismatch | T5 | post-acceptance doc sync per evidence rule + governance validator in CI (defined process) |

## Tasks
- **T1** single-definition + entity-boundary guard → tests/test_no_duplicate_defs.py (+entity distinctness asserts). Commit: `test: module-singleton + entity-boundary guard (REG-022, CORE-001)`
- **T2** canonical structured Story (CORE-002/003/004): pipeline renders from fields; scripts/normalize_drafts.py one-shot (backup first); metadata preserved per invariant. Tests: tests/test_canonical_story.py. Runtime: 5-story sample, channel parity. Commit: `feat: canonical structured story only (CORE-002/003/004)`
- **T4** GATE-11 invariant → tests/test_source_line_once.py. Commit: `feat: GATE-11 source attribution invariant`
- **T5** REG-026 sync: update 00-CURRENT-STATUS/01-MATRIX/GAP-AUDIT/04-CATALOG with Part-1 evidence; validator green. Commit: `docs: part-1 evidence sync (REG-026 process)`

## Exit
All seven assigned IDs DONE per evidence rule (each achievable without P3/4/6/8); validator PASS; channel formatting parity.
