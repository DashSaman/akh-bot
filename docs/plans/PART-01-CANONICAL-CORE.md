# PART-01 — CANONICAL CORE (plan, rev2 — full coverage)

Scope guard: structural ONLY. No event semantic matching, no claim paraphrase dedup, no burst aggregation (all Part 3). The live Trump/TIME micro-post incident stays untouched here.

## Coverage map (no orphan assignments)

| Requirement / Regression | Task(s) | Exit evidence |
|---|---|---|
| CORE-001 canonical entities exist | T1 | single-definition import guard green; repo scan: no entity class defined twice |
| CORE-002 no RawItem→publisher direct path | T2 | test_canonical_story: public render built ONLY from structured fields; no `**`/body blob in stored drafts (post-migration sample) |
| CORE-003 public output only from canonical Story | T2 | same test + renderer contract test; 5 newest prod stories verified field-only |
| CORE-004 StoryVersion model | T2 | structured fields include headline/lead/details + metadata (event_id, version, timestamps, language, topic, claim_refs, source_names); version bump test green |
| CORE-006 supporting entities (structural part) | T3 | media_cache gains explicit MediaAsset status labels (ORIGINAL_MEDIA / BRANDED_FALLBACK_CARD / MEDIA_REFERENCE_ONLY / MEDIA_NOT_ACCESSIBLE_IN_FALLBACK) shown on /admin/media; EvidenceLink/VerificationRun/PlatformAccount remain documented-missing (Part 4/8) — NOT built here |
| GATE-11 source attribution | T4 | test_source_line_once: known-source → exactly one «منبع:» line; unresolvable → SOURCE_NAME_RESOLUTION_ERROR hold (no silent publish) |
| REG-022 duplicate class shadows fix | T1 | permanent test_no_duplicate_defs (module source scan) |
| REG-026 docs/runtime mismatch | T5 | final sync task (see below) + governance validator in CI |

## Tasks

**T1 — single-definition guard (REG-022, CORE-001)**
- Files: tests/test_no_duplicate_defs.py — parse app/publishing/telegram_bot.py + app/newsroom/pipeline.py AST; assert exactly one top-level def/class per canonical name.
- Test: `python -m pytest tests/test_no_duplicate_defs.py -q`
- Commit: `test: module-singleton guard (REG-022 permanent)`

**T2 — canonical structured Story (CORE-002/003/004)**
- Invariant (per Part 0.1 §6): PUBLIC EDITORIAL CONTENT lives in structured fields (headline, lead, details[]). Story/StoryVersion legitimately also carries event_id, version, timestamps, language, topic, claim_refs, source_names, publication refs — these are metadata, NOT removed.
- Files: app/newsroom/pipeline.py (drop legacy `det["body"]` blob usage; render from fields), scripts/normalize_drafts.py (one-shot migration of stored drafts → fields, DB backup first).
- Tests: tests/test_canonical_story.py — (a) render contract: build_public_text receives fields only; (b) migration: sample draft has no preformatted blob; (c) version bump preserved.
- Runtime validation: after deploy, `docker exec` sample 5 newest stories: fields-only, channel output byte-identical (formatting parity check).
- Commit: `feat: canonical structured story only (CORE-002/003/004)`

**T3 — MediaAsset status labels (CORE-006 structural slice)**
- Files: app/publishing/media.py (status field), admin/media.html + media_views.py (label column).
- Tests: test_media labels; /admin/media shows label per row.
- Commit: `feat: media asset status labels (CORE-006 partial, REG-025)`

**T4 — GATE-11 source attribution invariant**
- Files: pipeline render path (assert names non-empty when eligible evidence exists; else hold with SOURCE_NAME_RESOLUTION_ERROR), tests/test_source_line_once.py.
- Commit: `feat: GATE-11 source attribution invariant`

**T5 — REG-026 final documentation sync (after live acceptance)**
- Update ONLY runtime-sensitive docs affected by Part 1: 00-CURRENT-STATUS (SHA/runtime truth), 01-REQUIREMENTS-MATRIX (CORE rows → DONE with new evidence + SHA), GAP-AUDIT (regenerate), 04-REGRESSION-CATALOG (REG-022 → FIXED+TESTED permanent, REG-026 → FIXED-for-Part1-scope with defined process: governance validator run in CI is the regression mechanism).
- Evidence rule: PART-1 rows flip to DONE only with code+test+runtime sample per INV-024.
- Commit: `docs: part-1 evidence sync (REG-026 process defined)`

## Exit
All assigned IDs DONE per evidence rule; validator green; channel unchanged beyond formatting parity; Part 3 prerequisites (structured fields) in place.
