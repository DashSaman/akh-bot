-- akh-bot initial schema (SQLite WAL). All timestamps are ISO-8601 UTC strings.

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('rss','telegram','x','website')),
    external_id TEXT,                    -- channel id / feed key / handle
    url TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'und',
    country TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    source_type TEXT NOT NULL DEFAULT 'news_organization',
    status TEXT NOT NULL DEFAULT 'DISCOVERED' CHECK (status IN ('APPROVED','DISCOVERED','BLOCKED')),
    enabled INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 50,
    polling_interval_min INTEGER NOT NULL DEFAULT 15,
    fetch_state TEXT NOT NULL DEFAULT '{}',  -- etag / last-modified etc.
    last_fetch_at TEXT,
    last_success_at TEXT,
    last_error TEXT,
    health_score REAL NOT NULL DEFAULT 1.0,  -- 0..1 reliability signal, never truth
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    activated_at TEXT                     -- backfill protection anchor; NULL until APPROVED
);

CREATE TABLE IF NOT EXISTS raw_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    platform TEXT NOT NULL,
    external_key TEXT NOT NULL,           -- stable per-platform message/guid key
    url TEXT NOT NULL DEFAULT '',
    canonical_url TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'und',
    author TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    edited_at TEXT,
    fetched_at TEXT NOT NULL,
    forward_from TEXT,                    -- lineage: forwarded-from channel id/url
    media_json TEXT NOT NULL DEFAULT '[]',
    lineage_key TEXT NOT NULL DEFAULT '', -- collapsed origin (forward/canonical domain)
    activation_ok INTEGER NOT NULL DEFAULT 0, -- 1 only if published_at >= source activated_at
    processed_state TEXT NOT NULL DEFAULT 'NEW' CHECK (processed_state IN ('NEW','PROCESSED','ERROR')),
    UNIQUE (source_id, external_key)
);

CREATE TABLE IF NOT EXISTS item_fingerprints (
    raw_item_id INTEGER PRIMARY KEY REFERENCES raw_items(id),
    canonical_url_hash TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    title_norm_hash TEXT NOT NULL DEFAULT '',
    simhash TEXT NOT NULL DEFAULT ''      -- hex of 64-bit simhash
);
CREATE INDEX IF NOT EXISTS idx_fp_url ON item_fingerprints(canonical_url_hash);
CREATE INDEX IF NOT EXISTS idx_fp_content ON item_fingerprints(content_hash);
CREATE INDEX IF NOT EXISTS idx_fp_title ON item_fingerprints(title_norm_hash);

CREATE TABLE IF NOT EXISTS item_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_item_id INTEGER NOT NULL REFERENCES raw_items(id),
    rev_no INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    edited_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (raw_item_id, rev_no)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    status TEXT NOT NULL DEFAULT 'NEW' CHECK (status IN ('NEW','CLUSTERED','READY','WRITTEN','PUBLISHED','HELD')),
    importance INTEGER NOT NULL DEFAULT 0,      -- 0..100 editorial weight
    velocity INTEGER NOT NULL DEFAULT 0,        -- reports/hour signal
    verification TEXT NOT NULL DEFAULT 'UNVERIFIED' CHECK (verification IN ('UNVERIFIED','SINGLE_SOURCE','CORROBORATED','CONFIRMED','CONFLICTING')),
    report_count INTEGER NOT NULL DEFAULT 0,
    independent_count INTEGER NOT NULL DEFAULT 0,
    languages_json TEXT NOT NULL DEFAULT '[]',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    processed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);

CREATE TABLE IF NOT EXISTS event_items (
    event_id INTEGER NOT NULL REFERENCES events(id),
    raw_item_id INTEGER NOT NULL REFERENCES raw_items(id),
    is_duplicate INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (event_id, raw_item_id)
);

CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id),
    text TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'UNVERIFIED' CHECK (state IN ('CONFIRMED','CORROBORATED','SINGLE_SOURCE','CONFLICTING','UNVERIFIED','RETRACTED')),
    risk_level TEXT NOT NULL DEFAULT 'normal' CHECK (risk_level IN ('normal','high')),
    supporting_json TEXT NOT NULL DEFAULT '[]',   -- [{item_id, source_id, quote}]
    contradicting_json TEXT NOT NULL DEFAULT '[]',
    independent_sources INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claims_event ON claims(event_id);

CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id),
    slug TEXT NOT NULL UNIQUE,
    headline TEXT NOT NULL,
    lead TEXT NOT NULL DEFAULT '',
    draft_json TEXT NOT NULL DEFAULT '{}',  -- full writer output incl. platform variants
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','PUBLISHED','CORRECTED','HELD')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    published_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_stories_event ON stories(event_id);

CREATE TABLE IF NOT EXISTS story_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL REFERENCES stories(id),
    version INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    change_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (story_id, version)
);

CREATE TABLE IF NOT EXISTS publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL REFERENCES stories(id),
    platform TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','SENT','FAILED','SKIPPED')),
    content_version INTEGER NOT NULL DEFAULT 1,
    payload_hash TEXT NOT NULL,
    remote_id TEXT,
    remote_url TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (story_id, platform, payload_hash)   -- idempotency: retries never duplicate
);
CREATE INDEX IF NOT EXISTS idx_pub_status ON publications(status, updated_at);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','done','failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    run_after TEXT NOT NULL,
    last_error TEXT,
    dedupe_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_due ON jobs(status, run_after);

CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key TEXT PRIMARY KEY,           -- sha256(model + prompt_version + messages)
    response_json TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
