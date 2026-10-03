-- MASTER-FINAL: canonical source identity + endpoint activation truth.
-- One real org/person = ONE identity (Entity ID from the owner XLSX is
-- authoritative); endpoints of the same identity never inflate independent
-- origin counts. endpoint_state records truthful activation per §17.
ALTER TABLE sources ADD COLUMN identity TEXT NOT NULL DEFAULT '';
ALTER TABLE sources ADD COLUMN endpoint_state TEXT NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE sources ADD COLUMN speed_tier TEXT NOT NULL DEFAULT '';
ALTER TABLE sources ADD COLUMN focus TEXT NOT NULL DEFAULT '';
-- precise XLSX role semantics (DB enum stays coarse; behavior columns rule)
ALTER TABLE sources ADD COLUMN role_detail TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_sources_identity ON sources(identity);

-- PART-8 CORE-009: platform account registry (per-platform config/health).
CREATE TABLE IF NOT EXISTS platform_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    account_id TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 0,
    auth_state TEXT NOT NULL DEFAULT 'NOT_CONFIGURED',
    health TEXT NOT NULL DEFAULT 'UNKNOWN',
    last_publish_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (platform, account_id)
);
