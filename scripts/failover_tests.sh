#!/bin/bash
# Real failover tests for 9Router combo rasteh-translation (host sqlite3).
set -e
DB=/opt/akhbot/9router-data/db/data.sqlite
K=$(grep '^OPENAI_COMPAT_API_KEY=' /opt/akhbot/.env | cut -d= -f2)

combo_sql() { # id name models_json
  python3 - "$1" "$2" "$3" <<'PY'
import sqlite3, sys, datetime
db = sqlite3.connect('/opt/akhbot/9router-data/db/data.sqlite')
now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
db.execute("INSERT OR REPLACE INTO combos (id, name, kind, models, createdAt, updatedAt) "
           "VALUES (?, ?, 'fallback', ?, ?, ?)",
           (sys.argv[1], sys.argv[2], sys.argv[3], now, now))
db.commit()
PY
}

cleanup() {
  python3 - <<'PY'
import sqlite3
db = sqlite3.connect('/opt/akhbot/9router-data/db/data.sqlite')
db.execute("DELETE FROM combos WHERE id LIKE 'ft-%'")
db.commit()
print("cleanup: remaining combos =", [r[0] for r in db.execute("SELECT name FROM combos")])
PY
  docker restart nine-router >/dev/null
  sleep 10
}
trap cleanup EXIT

ask() { # combo-name
  docker run --rm --network akhbot_internal -e NR_KEY="$K" \
    -v /opt/akhbot/app:/work -w /work --entrypoint python akhbot-app:latest \
    scripts/ninerouter_combo_test.py "$1" 2>/dev/null | tail -1
}

echo "== TEST A: #1 dead -> #2 serves =="
combo_sql ft-a rasteh-failtest-a '["groq/nonexistent-model-xyz","groq/openai/gpt-oss-120b"]'
docker restart nine-router >/dev/null; sleep 10
ask rasteh-failtest-a

echo "== TEST B: #1+#2 dead -> #3 (openrouter) serves =="
combo_sql ft-b rasteh-failtest-b '["groq/nonexistent-1","groq/nonexistent-2","openrouter/nvidia/nemotron-3.5-lightning:free"]'
docker restart nine-router >/dev/null; sleep 10
ask rasteh-failtest-b

echo "== TEST C: combo all-dead -> FreeAiRouter emergency direct groq =="
combo_sql ft-c rasteh-failtest-c '["groq/nonexistent-1"]'
docker restart nine-router >/dev/null; sleep 10
docker run --rm --network akhbot_internal --env-file /opt/akhbot/.env \
  -v akhbot_data:/data -v /opt/akhbot/app:/work -w /work -e PYTHONPATH=/work \
  --entrypoint python akhbot-app:latest -c "
from app.integrations.llm.router import FreeAiRouter
r = FreeAiRouter()
out = r.chat('rasteh-failtest-c', [{'role': 'user', 'content': 'Reply with the single word: OK'}])
print('ROUTER_RESULT:', (out or 'EMPTY')[:40])
" 2>/dev/null | tail -1
