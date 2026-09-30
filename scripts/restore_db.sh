#!/usr/bin/env bash
# Restore a backup into the akhbot data volume. Container is stopped for consistency,
# then started again. Usage: bash scripts/restore_db.sh /path/on/host/akhbot-XXXX.db
set -euo pipefail
BACKUP="${1:?usage: restore_db.sh <backup.db>}"
VOL_DIR=$(docker volume inspect akhbot_data --format '{{.Mountpoint}}')
docker stop akhbot-app
cp "$BACKUP" "$VOL_DIR/akhbot.db.restored"
mv "$VOL_DIR/akhbot.db" "$VOL_DIR/akhbot.db.pre-restore"
mv "$VOL_DIR/akhbot.db.restored" "$VOL_DIR/akhbot.db"
rm -f "$VOL_DIR/akhbot.db-wal" "$VOL_DIR/akhbot.db-shm"
docker start akhbot-app
sleep 3
curl -fsS http://127.0.0.1:8307/health && echo " -> restored & healthy"
