#!/usr/bin/env bash
# Online SQLite backup inside the akhbot-app container (safe under WAL) + retention.
set -euo pipefail
KEEP_DAYS="${KEEP_DAYS:-14}"
docker exec akhbot-app python - <<'PY'
import os, sqlite3, datetime
src = os.path.join(os.environ.get("DATA_DIR", "/data"), "akhbot.db")
backup_dir = os.path.join(os.environ.get("DATA_DIR", "/data"), "backups")
os.makedirs(backup_dir, exist_ok=True)
dest = os.path.join(backup_dir, f"akhbot-{datetime.datetime.utcnow():%Y%m%dT%H%M%SZ}.db")
conn = sqlite3.connect(src)
out = sqlite3.connect(dest)
with out:
    conn.backup(out)
out.close(); conn.close()
# retention
cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=14)
for f in os.listdir(backup_dir):
    p = os.path.join(backup_dir, f)
    try:
        if datetime.datetime.fromtimestamp(os.path.getmtime(p)) < cutoff:
            os.remove(p)
    except OSError:
        pass
print("backup:", dest)
PY
