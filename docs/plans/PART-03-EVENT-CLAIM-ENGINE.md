# PART-03 — EVENT/CLAIM ENGINE (rev4, design-hardened @PART-3.0)

Scope guard: PART 3 owns CLAIM-001/002/003, EVENT-001/002/003, PUB-003, GATE-03/05/06, REG-028/029/031/034/036..040 (REG-030 stays guarded). Explicitly NOT here: verification-history (P4), translation/AI (P5), media (P6), admin (P7), multi-platform (P8). PART 3 depends only on PART 1 (canonical Story) — may execute while INGEST-003 BLOCKED_EXTERNAL.

## Coverage map (no orphan IDs/REGs)

| ID / REG | Subpart(s) | Test-first fixture |
|---|---|---|
| CLAIM-001 structured atomic claims | P3-A | test_claim_model.py (fields: actor/predicate/object/qualifiers/location/time/quantity/attribution/certainty/negation/source_ref) |
| CLAIM-002 completeness gate + GATE-03 class-aware slots | P3-A | test_claim_completeness.py: QUOTE(speaker+statement)/ATTACK(action+target)/CASUALTY(context+count+attr)/MARKET(asset+move+time)/INTERNET(area+state); unknown-actor allowed; fragments table below → all FAIL |
| CLAIM-003 dedup pipeline A→D | P3-C | test_claim_dedup.py (§14 stages; contradiction table §16) |
| GATE-06 claim comparison states | P3-C | SAME_CLAIM/NEW_CLAIM/POTENTIAL_CONTRADICTION/AMBIGUOUS_CLAIM (never force ambiguous→SAME) |
| EVENT-001 multi-signal identity | P3-B | test_event_identity.py (EventFingerprint §3; wording-change REG-040; hard-conflict table §4) |
| GATE-05 three-way decision | P3-B | ATTACH_EXISTING/CREATE_NEW/AMBIGUOUS_EVENT (§5; ambiguity never merges) |
| EVENT-002 same-event→EDIT invariant | P3-E | test_edit_vs_send.py (§21 architectural guard: publication-exists⇒EDIT-only job type) |
| EVENT-003 burst/continuation windows | P3-D | test_burst_context.py (§7 separate windows; context types §6; TTL §19) |
| PUB-003 importance floor audit | P3-F | test_importance_audit.py (§27 distribution fixtures, not eyeballing) |
| REG-028 micro-post flood | P3-B+E | six-fragment fixture (§11: 6 RawItems → N≤6 complete claims → 1 Event → 1 Story → 1 SEND) |
| REG-029 interview multi-post | P3-B/D | interview continuation: hours allowed (§6) |
| REG-031 incomplete prefix | P3-A/D | §34 fixture: prefix → CONTEXT_ONLY, 0 claim/event/story/pub |
| REG-034 low-value flood | P3-F | floor audit + fixtures |
| REG-036 new claim→new post | P3-E | materiality §23 + §33 (2 material claims → 0 SEND, 1 debounced EDIT) |
| REG-037 no burst aggregation | P3-D | burst window aggregation fixtures |
| REG-038 paraphrase dup | P3-C | §32 same-quote paraphrase → 1 claim (fingerprint convergence §15) |
| REG-039 contextless quote | P3-D | context inheritance rules §18 |
| REG-040 wording→identity | P3-B | headline NEVER in fingerprint (§3) |

## Subparts (each: reqs/regressions/files/test-first/migration/commit/runtime/rollback)

### P3-A Claim model + completeness (CLAIM-001, CLAIM-002, GATE-03, REG-031)
- Files: app/newsroom/claim_model.py (StructuredClaim dataclass + ClaimClass), claim_completeness.py
- Migration 009: claims add columns actor/predicate/object/qualifiers/location/time_ref/quantity/attribution/certainty/negation/claim_class/fingerprint/source_item_id
- Tests first (§9 slot tables, §10 fragment blacklist: «ترامپ:», «ترامپ به مجله تایم:», «فوری:», «عاجل:», «منابع عبری:», «در همین حال:» → CONTEXT_ONLY, publishable=never-alone)
- Commit: `feat(P3-A): structured claim model + class-aware completeness`
- Runtime acceptance: replay fixture set; 0 publications from fragments
- Rollback: EVENT_ENGINE_V2_ENABLED=false (claim parser bypassed, old text-claims remain)

### P3-B Event identity + candidate matcher (EVENT-001, GATE-05, REG-028/029/040)
- EventFingerprint dims (§3): actors, predicate, object/target, location, event_type, topic, conversation/thread context, temporal bucket, explicit occurrence-id (interview/speech name) — NEVER headline text, NEVER time alone
- Match score (§4): per-dimension table (not one magic number) + HARD-CONFLICT signals (different exclusive location/target/occurrence-id/event-type, explicit «حمله دوم/جداگانه», >continuation window) ⇒ CREATE_NEW regardless of score
- Decision (§5): ATTACH_EXISTING / CREATE_NEW / AMBIGUOUS_EVENT (material ambiguity ⇒ provisional separate event, never contaminate)
- Context types (§6) with per-type continuation policy: INTERVIEW(hours)/PRESS_CONF/SPEECH/LIVE_INCIDENT(short)/MILITARY_STRIKE(strict: 2nd strike 3h later = NEW unless same occurrence-id)/POLITICAL_ANNOUNCEMENT/MARKET_MOVE/INTERNET_OUTAGE/GENERAL_NEWS
- Performance (§39): candidate retrieval bounded — index (event_type, primary_actor_norm, last_seen window [continuation policy], state OPEN); never O(all-history)
- Files: app/newsroom/event_fingerprint.py, event_matcher.py; migration 010: events add fingerprint_json/event_type/context_ref/state/epoch
- Tests first: §31 over-merge negatives (2 strikes stay 2; 2 Trump announcements stay 2; same actor+topic diff action stay separate) + §32 under-merge positives + §49 A/B/G/I cases
- Commit: `feat(P3-B): multi-signal event identity + three-way matcher`
- Rollback: V2 flag off

### P3-C Claim dedup + contradiction protection (CLAIM-003, GATE-06, REG-038)
- Pipeline (§14): A exact canonical fingerprint → B structured-field equality → C lexical (bounded) → D semantic-lite deterministic (negation/number/actor/target/location guards §16)
- Normalization (§13): unify ar/fa variants, ZWNJ, emojis, boilerplate, speaker-prefix — NEVER strip negation/numbers/dates/names/modals («نیست/نخواهد/ممکن است/گفته می‌شود»)
- Critical-diff blocklist: differing number/negation/actor/target/location ⇒ POTENTIAL_CONTRADICTION (kept distinct; handling itself = Part 4)
- States (§17): SAME_CLAIM / NEW_CLAIM / POTENTIAL_CONTRADICTION / AMBIGUOUS_CLAIM
- Files: app/newsroom/claim_compare.py; index claims(fingerprint) unique-per-event
- Tests first: §16 triple table + paraphrase-convergence §15 + §49 C/D/H
- Commit: `feat(P3-C): multi-stage claim comparison with contradiction guards`

### P3-D Source context + burst aggregation (EVENT-003, REG-037/039, fragment contexts)
- Context inheritance (§18): same source + SOURCE_CONTEXT_TTL_SECONDS window + no intervening topic-marker; inherited speaker/context recorded on claim; never global
- Reset on (§19): topic change / new explicit speaker / event marker / large gap / category switch
- Windows separate (§7): EVENT_BURST_WINDOW_SECONDS (aggregate fragments before first SEND in normal mode) ≠ EVENT_CONTINUATION_WINDOW_MINUTES (follow-up evidence attach, per event-type)
- Files: app/newsroom/source_context.py, burst.py
- Tests: §49 E/F; prefix→next-complete inheritance; unrelated switch resets
- Commit: `feat(P3-D): bounded source context + burst aggregation`

### P3-E Story evolution + SEND/EDIT invariant (EVENT-002, REG-028/036)
- §20: new unique claim → evidence link + Story fields update + StoryVersion++ ; if publication SENT exists ⇒ enqueue EDIT job ONLY
- §21 architectural guard: distinct job types publish_send vs publish_edit; publish_send precondition = ledger has NO SENT for (story,platform) — enforced in runner + test_publication_paths AST guard extension; accidental SEND-per-claim impossible
- §22 selection: headline=top claim; details=selected distinct meaningful claims; MAX_PUBLIC_STORY_DETAILS cap (config, fixture-tested)
- Files: app/newsroom/story_evolution.py; jobs/runner.py (edit-only path guard)
- Tests: §33 (6 fragments → 1 SEND; +2 material claims → StoryVersion++, 0 SEND, 1 EDIT)
- Commit: `feat(P3-E): story evolution + hard SEND/EDIT invariant`

### P3-F Importance/materiality/debounce (PUB-003, REG-034/036)
- §27 audit script: last-N items distribution (topic/score/published/desired-class) → tune floor ONLY via fixture expectations; priority never trust
- §23 MATERIAL_PUBLIC_UPDATE rules (new casualty/target/official confirmation/meaning-changing quote/status transition = material; restatement/paraphrase/minor detail = not)
- §24 PUBLIC_EDIT_
