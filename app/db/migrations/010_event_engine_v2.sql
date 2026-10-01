-- PART-3-B (P3-B): event structural fields for the V2 engine — nullable, no
-- semantic backfill, no regrouping of legacy events, no historical rewrite.
ALTER TABLE events ADD COLUMN fingerprint_json TEXT;
ALTER TABLE events ADD COLUMN event_type TEXT;
ALTER TABLE events ADD COLUMN context_ref TEXT;
ALTER TABLE events ADD COLUMN state TEXT;
ALTER TABLE events ADD COLUMN epoch TEXT;
CREATE INDEX IF NOT EXISTS idx_events_v2_retrieval
  ON events(event_type, state, last_seen_at);
