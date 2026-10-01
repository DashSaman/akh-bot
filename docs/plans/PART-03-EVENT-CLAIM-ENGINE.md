# PART-03 — EVENT/CLAIM ENGINE (plan)

Goal: kill the micro-post flood. 6 messages → 1 Event → 1 evolving Story → 1 Telegram message.

## Design decisions (to implement, test-first)
- **EVENT_IDENTITY**: event key = (primary entity pair e.g. speaker↔topic, category, recency window) — NOT headline text (REG-040).
- **EVENT_BURST_WINDOW_SECONDS** (default 300) + **EVENT_CONTINUATION_WINDOW_MINUTES** (default 180): items from same source/lineage within window attach to open event unless a *distinct* completeness-passing claim of a *different* real-world occurrence.
- **GATE-03 CLAIM_COMPLETENESS**: WHO+WHAT(+WHERE/WHEN when the claim class demands); speaker-prefix/intro line = metadata → CLAIM_INCOMPLETE.
- **GATE-06 CLAIM_DEDUP**: normalized token-set Jaccard ≥0.7 vs existing claims of event → merge (evidence link appended, no new claim).
- **SAME_STORY_UPDATE_MODE**: new claim for public event → StoryVersion++ → ledger EDIT same Telegram message (existing edit path), never new post.
- **HIGH_PRIORITY_BREAKING_MODE**: topic≥90 + complete claim → publish immediately; later claims merge+edit (no delay for urgent complete story).

## Tasks
1. T1 tests/test_claim_completeness.py (fixtures: «ترامپ به مجله تایم:» FAIL; «ترامپ گفت در صورت X ی خواهد شد» PASS; quote fragment FAIL) → implement gates/claim_completeness.py.
2. T2 tests/test_event_burst.py: 6 Yashar-TIME-excerpt fixtures (staggered 90s) → assert 1 event, 1 story, 6 claims, 1 publication job; paraphrase pair → 1 claim (REG-038); wording-change headline → same event id (REG-040).
3. T3 pipeline wiring: claim merge updates story version → enqueue edit-only job; GATE-12 floor tuning (LOW_PUBLICATION_VALUE audit from last-200-posts data).
4. T4 runtime acceptance (Constitution §P): replay last 24h real NAYA/Yashar raw_items through engine in shadow mode; measure would-be posts (target: micro-post flood 0 vs today's baseline), then enable.

## Exit (verbatim from Constitution)
interview-split → 1 Event; paraphrase → 1 Claim; new claim → same Story; public story → same message edited; incomplete quote → not published; micro-post flood = 0 (live evidence, INV-024).
