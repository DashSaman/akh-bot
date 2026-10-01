ALTER TABLE sources ADD COLUMN tg_stable_id TEXT;
-- PART-2 T1: persistent source checkpoints + SLA state (canonical names).
-- last_remote_id: watermark that may only advance AFTER the item is durably persisted.
ALTER TABLE sources ADD COLUMN last_remote_id INTEGER;
ALTER TABLE sources ADD COLUMN last_remote_ts TEXT;
ALTER TABLE sources ADD COLUMN last_processed_item INTEGER;
ALTER TABLE sources ADD COLUMN last_item_at TEXT;
ALTER TABLE sources ADD COLUMN next_check_at TEXT;
-- Backfill (idempotent): seed checkpoint from existing fetch_state watermark;
-- telethon-web keys are tgweb:<chat>/<msg> so numeric tail = remote message id.
UPDATE sources SET last_remote_id = COALESCE(
    CAST(json_extract(fetch_state, '$.watermark') AS INTEGER), last_remote_id)
WHERE last_remote_id IS NULL AND json_extract(fetch_state, '$.watermark') IS NOT NULL;
UPDATE sources SET last_check_at = COALESCE(last_check_at, last_fetch_at)
WHERE last_check_at IS NULL AND last_fetch_at IS NOT NULL;
