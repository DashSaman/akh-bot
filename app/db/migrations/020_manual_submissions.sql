-- E6: editorial submissions audit trail — every admin item enters the SAME
-- canonical pipeline (RawItem -> Event -> Story -> publication), no direct send.
CREATE TABLE IF NOT EXISTS manual_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submitter_admin_id INTEGER NOT NULL REFERENCES bot_admins(id),
    telegram_chat_id TEXT NOT NULL DEFAULT '',
    telegram_message_id TEXT NOT NULL DEFAULT '',
    telegram_media_group_id TEXT NOT NULL DEFAULT '',
    forwarded_origin TEXT NOT NULL DEFAULT '',
    raw_item_id INTEGER,
    story_id INTEGER,
    preview_message_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'RECEIVED'
        CHECK (status IN ('RECEIVED','PREVIEW','SUBMITTED','HELD','PUBLISHED',
                          'CANCELLED','REJECTED')),
    created_at TEXT NOT NULL DEFAULT '',
    approved_at TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_manual_submissions_group
    ON manual_submissions(telegram_media_group_id);
