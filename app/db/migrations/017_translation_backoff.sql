-- 017_translation_backoff: per-event translation retry backoff (THRASH-FIX)
-- Held NEEDS_LANGUAGE_PROCESSING events requeued every pass (~3min) exhausted
-- the free-tier AI pool. These columns add exponential backoff + attempt count.
ALTER TABLE events ADD COLUMN translate_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE events ADD COLUMN next_translate_at TEXT NOT NULL DEFAULT '';
