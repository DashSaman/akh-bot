-- Priority queue: breaking updates must not queue behind stale backlog.
ALTER TABLE jobs ADD COLUMN priority INTEGER NOT NULL DEFAULT 60;
-- Freshness gate fields for publication suppression of stale content
ALTER TABLE events ADD COLUMN last_verified_at TEXT;
ALTER TABLE events ADD COLUMN verification_attempts INTEGER NOT NULL DEFAULT 0;
