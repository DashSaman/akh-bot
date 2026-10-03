-- PART-4: verification lifecycle — canonical EvidenceLink (CORE-007) +
-- traceable VerificationRun (CORE-008). Additive only; no historical rewrite:
-- legacy claims keep their JSON evidence blobs and get NO synthetic links
-- (provenance is never invented). Idempotency via UNIQUE keys so replays and
-- the 5-minute reverify loop can never duplicate rows.

CREATE TABLE IF NOT EXISTS evidence_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL REFERENCES claims(id),
    raw_item_id INTEGER NOT NULL REFERENCES raw_items(id),
    source_id INTEGER NOT NULL REFERENCES sources(id),
    lineage_key TEXT NOT NULL DEFAULT '',   -- collapsed origin (forward/canonical domain)
    relation TEXT NOT NULL CHECK (relation IN ('SUPPORTS','CONTRADICTS','CONTEXT')),
    observed_at TEXT,                       -- item published_at/fetched_at
    created_at TEXT NOT NULL,
    UNIQUE (claim_id, raw_item_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_evidence_links_claim ON evidence_links(claim_id);
CREATE INDEX IF NOT EXISTS idx_evidence_links_origin ON evidence_links(claim_id, lineage_key);

CREATE TABLE IF NOT EXISTS verification_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id),
    claim_id INTEGER REFERENCES claims(id), -- NULL = event-level run
    started_at TEXT NOT NULL,
    completed_at TEXT,
    trigger TEXT NOT NULL CHECK (trigger IN ('NEW_EVIDENCE','SCHEDULED_REVERIFY','CONTRADICTION','DEADLINE','MANUAL')),
    result TEXT NOT NULL,                   -- claim/event state or resolution outcome
    independent_origin_count INTEGER NOT NULL DEFAULT 0,
    support_count INTEGER NOT NULL DEFAULT 0,
    contradiction_count INTEGER NOT NULL DEFAULT 0,
    high_risk INTEGER NOT NULL DEFAULT 0,
    reason_codes TEXT NOT NULL DEFAULT '',
    next_verify_at TEXT,
    dedupe_key TEXT UNIQUE                  -- one run per scheduled attempt, ever
);
CREATE INDEX IF NOT EXISTS idx_vruns_event ON verification_runs(event_id, started_at);
CREATE INDEX IF NOT EXISTS idx_vruns_claim ON verification_runs(claim_id, started_at);

-- claim-level reverify bookkeeping (canonical equivalents per §9)
ALTER TABLE claims ADD COLUMN last_verified_at TEXT;
ALTER TABLE claims ADD COLUMN next_verify_at TEXT;
ALTER TABLE claims ADD COLUMN verification_attempts INTEGER NOT NULL DEFAULT 0;
