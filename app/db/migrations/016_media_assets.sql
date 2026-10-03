-- PART-6: canonical MediaAsset with TRUTHFUL status labels (CORE-006,
-- REG-025). A branded fallback card is never an original source photo;
-- checksum dedup via UNIQUE(sha256); assets attach to canonical Story/Event.

CREATE TABLE IF NOT EXISTS media_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER REFERENCES stories(id),
    event_id INTEGER REFERENCES events(id),
    raw_item_id INTEGER REFERENCES raw_items(id),
    source_id INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL CHECK (kind IN ('photo','video','card')),
    status TEXT NOT NULL CHECK (status IN ('ORIGINAL_MEDIA','SOURCE_REFERENCE','BRANDED_FALLBACK','UNAVAILABLE')),
    sha256 TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    remote_url TEXT NOT NULL DEFAULT '',
    size_mb REAL NOT NULL DEFAULT 0,
    caption_ref TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (sha256)
);
CREATE INDEX IF NOT EXISTS idx_media_assets_story ON media_assets(story_id, status);
CREATE INDEX IF NOT EXISTS idx_media_assets_event ON media_assets(event_id, status);

-- PART-10 GROWTH-001: cookieless aggregate analytics (no personal data)
CREATE TABLE IF NOT EXISTS analytics_events (
    day TEXT NOT NULL,
    path_class TEXT NOT NULL,
    referrer_host TEXT NOT NULL DEFAULT '-',
    utm TEXT NOT NULL DEFAULT '-|-|-',
    views INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (day, path_class, referrer_host, utm)
);
CREATE INDEX IF NOT EXISTS idx_analytics_day ON analytics_events(day);
