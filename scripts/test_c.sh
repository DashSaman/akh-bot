#!/bin/bash
# Test C: 9Router combo all-dead -> FreeAiRouter emergency direct provider.
set -e
python3 - <<'PY'
import sqlite3, datetime
db = sqlite3.connect('/opt/akhbot/9router-data/db/data.sqlite')
now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
db.execute("INSERT OR REPLACE INTO combos (id, name, kind, models, createdAt, updatedAt) "
           "VALUES ('ft-c','rasteh-failtest-c','fallback','[\"groq/nonexistent-1\"]', ?, ?)",
           (now, now))
db.commit()
print("ft-c set")
PY
docker restart nine-router >/dev/null
sleep 12
docker run --rm --network akhbot_internal --env-file /opt/akhbot/.env \
  -v akhbot_data:/data -v /opt/akhbot/app:/work -w /work -e PYTHONPATH=/work \
  --entrypoint python akhbot-app:latest scripts/test_c_emergency.py 2>&1 | tail -1
python3 - <<'PY'
import sqlite3
db = sqlite3.connect('/opt/akhbot/9router-data/db/data.sqlite')
db.execute("DELETE FROM combos WHERE id LIKE 'ft-%'")
db.commit()
print("cleanup:", [r[0] for r in db.execute("SELECT name FROM combos")])
PY
docker restart nine-router >/dev/null
sleep 10
echo "9router_back"
