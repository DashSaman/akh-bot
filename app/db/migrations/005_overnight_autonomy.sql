-- Overnight autonomy: 60-minute resolution + source SLA + soak markers.
ALTER TABLE sources ADD COLUMN last_check_at TEXT;
ALTER TABLE sources ADD COLUMN consecutive_failures INTEGER NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS media_cache (
    path TEXT PRIMARY KEY, story_id INTEGER, sha TEXT, size_mb REAL,
    created_at TEXT NOT NULL, published_at TEXT
);
