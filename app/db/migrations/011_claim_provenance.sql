-- PART-3-C (P3-C): claim provenance junction — dedup never discards evidence.
CREATE TABLE IF NOT EXISTS claim_source_items (
    claim_id INTEGER NOT NULL REFERENCES claims(id),
    source_item_id INTEGER NOT NULL REFERENCES raw_items(id),
    created_at TEXT NOT NULL,
    UNIQUE(claim_id, source_item_id)
);
CREATE INDEX IF NOT EXISTS idx_csi_item ON claim_source_items(source_item_id);
