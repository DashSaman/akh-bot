-- E2: multi-admin editorial bot — immutable Telegram numeric user_id auth.
CREATE TABLE IF NOT EXISTS bot_admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'EDITOR' CHECK (role IN ('OWNER','EDITOR','PUBLISHER')),
    enabled INTEGER NOT NULL DEFAULT 1,
    can_submit INTEGER NOT NULL DEFAULT 1,
    can_publish INTEGER NOT NULL DEFAULT 1,
    can_edit INTEGER NOT NULL DEFAULT 1,
    can_cancel INTEGER NOT NULL DEFAULT 1,
    can_manage_admins INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
