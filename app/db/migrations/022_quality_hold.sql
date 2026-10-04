-- §QUALITY: explicit quality-hold reason. The verification column has a
-- hard CHECK limited to claim states; quality gates get their own additive
-- column so holds persist without any destructive rebuild.
ALTER TABLE events ADD COLUMN quality_hold TEXT NOT NULL DEFAULT '';
