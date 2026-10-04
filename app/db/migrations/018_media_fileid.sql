-- 018_media_fileid: FINAL MEDIA policy — reuse Telegram file_id, keep
-- size/dimensions metadata; source media bytes are NEVER stored long-term.
ALTER TABLE media_assets ADD COLUMN telegram_file_id TEXT NOT NULL DEFAULT '';
ALTER TABLE media_assets ADD COLUMN meta_json TEXT NOT NULL DEFAULT '';
