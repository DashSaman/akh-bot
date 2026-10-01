# PART-01 — CANONICAL CORE (plan)

Goal: every public render originates ONLY from structured Story fields; single module definitions; source-line invariant testable.

## Tasks (test-first)
1. **T1 single-definition import guard**
   - Files: tests/test_no_duplicate_defs.py (new): asserts one `class TelegramBotPublisher`, one `def build_public_text` etc. via source scan of app/publishing/telegram_bot.py.
   - Test: `python -m pytest tests/test_no_duplicate_defs.py -q`
   - Runtime: none (pure guard for REG-022).
   - Commit: `test: module-singleton guard (REG-022)`
2. **T2 purge legacy body-blob fields**
   - Files: app/newsroom/pipeline.py (`det["body"]` usages → headline/lead/details), stories drafts migration script scripts/normalize_drafts.py (one-shot, backup first).
   - Tests: tests/test_canonical_story.py — story draft contains ONLY headline/lead/details/source_names/lifecycle; renderer builds text from fields (fails if body blob present).
   - Runtime validation: docker exec — sample 5 newest stories: no `**` inside stored fields; channel unchanged.
   - Commit: `feat: canonical structured story only (CORE-002/003)`
3. **T3 source-line invariant**
   - Files: render path asserts source_names non-empty when eligible items exist else SOURCE_NAME_RESOLUTION_ERROR hold.
   - Tests: test_source_line_once (known-source → exactly one منبع; unknown → hold state).
   - Commit: `feat: GATE-11 source attribution invariant`
## Exit
All CORE matrix rows → DONE; REG-009/010/015 permanent tests green; no behavior change on channel beyond formatting parity.
