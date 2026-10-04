-- §SRC: self-service source control — polling tier, publication policy,
-- per-admin source-management permission, and an audit trail.
-- Idempotent: some columns already exist in upgraded production schemas.
ALTER TABLE sources ADD COLUMN polling_tier TEXT NOT NULL DEFAULT 'NORMAL';
ALTER TABLE bot_admins ADD COLUMN can_manage_sources INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS source_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id INTEGER,
    old_value TEXT NOT NULL DEFAULT '',
    new_value TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
