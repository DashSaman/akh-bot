# Data Model (SQLite — see `app/db/migrations/001_init.sql` for authoritative DDL)

| Table | Purpose | Key invariants |
|---|---|---|
| `sources` | admin-controlled whitelist | status APPROVED/DISCOVERED/BLOCKED; `activated_at` anchors backfill protection; `health_score` is a signal, never truth |
| `raw_items` | immutable raw evidence | `UNIQUE(source_id, external_key)`; `activation_ok=0` → STORE_ONLY; `lineage_key` collapses copies to origin |
| `item_fingerprints` | dedup keys | canonical URL hash, content hash, normalized title hash, 64-bit SimHash |
| `item_revisions` | edit history | append-only revisions of external posts (originals preserved) |
| `events` | real-world events | report_count (all reports) vs independent_count (distinct origins); status NEW→CLUSTERED→READY→WRITTEN→PUBLISHED/HELD |
| `event_items` | membership | `is_duplicate` marks collapsed copies |
| `claims` | atomic claims | state CONFIRMED/CORROBORATED/SINGLE_SOURCE/CONFLICTING/UNVERIFIED/RETRACTED; risk normal/high; supporting/contradicting evidence JSON |
| `stories` | generated Persian story | one master story per event (slug stable); versions in `story_versions` |
| `story_versions` | correction transparency | full snapshots with change notes |
| `publications` | ledger | `UNIQUE(story_id, platform, payload_hash)` → retries never duplicate; remote message ids stored |
| `jobs` | durable outbox | pending/running/done/failed; exponential backoff; `dedupe_key` prevents duplicate enqueues |
| `llm_cache` | response cache | keyed by sha256(model+prompt_version+messages); records tokens/latency |
| `settings` | runtime switches | `pause_all`, `pause_platform:*`, `schema_version` |

Timestamps are ISO-8601 UTC strings. Migration path: repositories are the only SQL
boundary — swap `app/db/` for PostgreSQL (+pgvector) without touching business logic.


## Canonical entity spec (Constitution §N)
Source / RawItem(immutable evidence) / MediaAsset / Claim(atomic assertion) / Event(real-world grouping) / EvidenceLink / VerificationRun / Story(editorial representation) / StoryVersion(evolving public state) / PublicationJob / PublicationLedger / PlatformAccount.
Rules: one Event ↔ many RawItems/Claims؛ one Story evolves many Versions؛ **never recreate a Publication merely because a new RawItem arrives** (update Story→edit same remote message). Present-in-code: Source,RawItem,Claim,Event,Story,StoryVersion,Publication(jobs+ledger merged),media_cache(asset partial)؛ Missing entities: EvidenceLink,VerificationRun,PlatformAccount (Part 1/4/8).
