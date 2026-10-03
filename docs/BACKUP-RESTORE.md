# Backup & Restore

- **Backup:** `bash scripts/backup_db.sh` — SQLite online backup API inside the
  running container (safe under WAL, no downtime), written to `akhbot_data`
  volume `/data/backups/`, 14-day retention. Recommended cron: `15 3 * * *`.
- **Pre-migration backup:** before applying any new migration, run the same script.
- **Restore:** `bash scripts/restore_db.sh <backup.db>` — stops the container,
  swaps the DB (keeps `.pre-restore` copy), clears WAL/SHM, restarts, health-checks.
- **Tested:** restore round-trip verified by `tests/test_backup.py` (backup contains
  exactly the pre-backup state; source DB unaffected). Full production restore
  drill is scheduled post-credentials (see ROADMAP).
- **What is backed up:** SQLite only (all state). Media policy stores URLs, not
  mirrors — nothing else is stateful.

## MASTER-FINAL: تمرین DR اثبات‌شده (P9)
`bash scripts/dr_drill.sh <backup.db>` — بازیابی در volume ایزوله (هرگز روی DB زنده):
تمام جداول canonical + watermarkها + mappingهای remote + تنظیمات (بدون secret) تأیید؛
مهاجرت‌ها no-op؛ بوت اپ روی DB بازیابی‌شده سالم؛ سپس پاک‌سازی کامل منابع ایزوله.
آخرین دریل: 2026-10-03 — PASS (also 12/12 portability checks live).
