-- PART-3-D (P3-D): per-source bounded context + burst-group persistence.
-- Bounded state: exactly ONE live context row per source (UNIQUE(source_id),
-- upsert). Burst membership is idempotent via UNIQUE(raw_item_id) — an item
-- belongs to exactly one burst group, retries/replays cannot duplicate.
-- Dormant until wired by P3-E; EVENT_ENGINE_V2_ENABLED stays false and no
-- historical story/event/claim/publication data is touched or regrouped.

CREATE TABLE IF NOT EXISTS source_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL UNIQUE REFERENCES sources(id),
    speaker TEXT NOT NULL DEFAULT '',      -- explicit speaker label («ترامپ به مجله تایم»)
    context_ref TEXT NOT NULL DEFAULT '',  -- interview/speech reference (verbatim label)
    topic_tokens TEXT NOT NULL DEFAULT '[]',  -- JSON array of normalized tokens
    event_type TEXT NOT NULL DEFAULT 'GENERAL_NEWS',
    raw_item_id INTEGER REFERENCES raw_items(id),  -- prefix item that established it
    reason_code TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL               -- created_at + SOURCE_CONTEXT_TTL_SECONDS
);
CREATE INDEX IF NOT EXISTS idx_source_context_expiry ON source_context(expires_at);

CREATE TABLE IF NOT EXISTS burst_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    event_type TEXT NOT NULL DEFAULT 'GENERAL_NEWS',
    context_ref TEXT NOT NULL DEFAULT '',
    speaker TEXT NOT NULL DEFAULT '',
    topic_tokens TEXT NOT NULL DEFAULT '[]',  -- JSON array, union-merged as members join
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_burst_groups_source ON burst_groups(source_id, last_seen_at);

CREATE TABLE IF NOT EXISTS burst_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    burst_group_id INTEGER NOT NULL REFERENCES burst_groups(id),
    raw_item_id INTEGER NOT NULL UNIQUE REFERENCES raw_items(id),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_burst_members_group ON burst_members(burst_group_id);
