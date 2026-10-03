-- PART-3-F (P3-F): materiality markers on claims — drives the EDIT-vs-store
-- publication decision (§23). Additive only; historical claims default to
-- material=0 (never re-publicized retroactively).

ALTER TABLE claims ADD COLUMN material INTEGER NOT NULL DEFAULT 0;
ALTER TABLE claims ADD COLUMN material_reasons TEXT NOT NULL DEFAULT '';
