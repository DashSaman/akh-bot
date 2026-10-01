-- PART-3-A (P3-A): structured claim columns — nullable, no semantic backfill,
-- no UNIQUE constraint (P3-C owns dedup), no behavior change. Legacy claim text
-- and all evidence preserved verbatim.
ALTER TABLE claims ADD COLUMN actor TEXT;
ALTER TABLE claims ADD COLUMN predicate TEXT;
ALTER TABLE claims ADD COLUMN object TEXT;
ALTER TABLE claims ADD COLUMN qualifiers TEXT;
ALTER TABLE claims ADD COLUMN location TEXT;
ALTER TABLE claims ADD COLUMN time_ref TEXT;
ALTER TABLE claims ADD COLUMN quantity TEXT;
ALTER TABLE claims ADD COLUMN attribution TEXT;
ALTER TABLE claims ADD COLUMN certainty TEXT;
ALTER TABLE claims ADD COLUMN negation INTEGER;
ALTER TABLE claims ADD COLUMN claim_class TEXT;
ALTER TABLE claims ADD COLUMN fingerprint TEXT;
ALTER TABLE claims ADD COLUMN source_item_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_claims_fingerprint ON claims(fingerprint);
CREATE INDEX IF NOT EXISTS idx_claims_source_item ON claims(source_item_id);
