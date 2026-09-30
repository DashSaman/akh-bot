-- Source trust split: ingestion is technical; verification trust is owner-granted.
-- Existing sources default to NOT verification-approved (owner must approve each).
ALTER TABLE sources ADD COLUMN verification_allowed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sources ADD COLUMN source_role TEXT NOT NULL DEFAULT 'MAJOR_NEWSROOM'
  CHECK (source_role IN ('OFFICIAL_PRIMARY','MAJOR_NEWSROOM','JOURNALIST','LOCAL_SOURCE','AGGREGATOR'));
ALTER TABLE sources ADD COLUMN can_increase_independent_count INTEGER NOT NULL DEFAULT 1;
