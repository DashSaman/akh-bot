#!/usr/bin/env bash
# verify_instance.sh — single read-only post-migration verification (NO secrets).
# Usage: bash /opt/akhbot/app/scripts/verify_instance.sh
# Exit 0 = all critical PASS; non-zero = critical migration requirement failed.
set -uo pipefail
APP=/opt/akhbot/app
fail=0
line() { printf '%-30s %s\n' "$1" "$2"; }
ck()   { case "$2" in PASS*) line "$1" "$2";; *) line "$1" "FAIL ($2)"; fail=1;; esac; }

REPO=$(git -C "$APP" rev-parse --short HEAD 2>/dev/null || echo "?")
IMG=$(docker exec akhbot-app printenv AKHBOT_GIT_SHA 2>/dev/null || echo "?")
ck "git/image SHA match" "$([ "$REPO" = "$IMG" ] && echo PASS || echo "repo=$REPO img=$IMG")"

DBOK=$(docker exec akhbot-app python -c "
import sqlite3, sys
c = sqlite3.connect('/data/akhbot.db')
tables = {r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")}
need = {'sources','raw_items','events','stories','publications','jobs','item_fingerprints'}
print('PASS' if need <= tables else 'missing:'+str(sorted(need-tables)))" 2>/dev/null || echo ERR)
ck "db schema" "$DBOK"

REG=$(docker exec akhbot-app python -c "
import sqlite3
c = sqlite3.connect('/data/akhbot.db')
print('PASS n=%d approved=%d' % (c.execute('SELECT COUNT(*) FROM sources').fetchone()[0],
      c.execute(\"SELECT COUNT(*) FROM sources WHERE status='APPROVED'\").fetchone()[0]))" 2>/dev/null || echo ERR)
ck "source registry" "$REG"

WM=$(docker exec akhbot-app python -c "
import sqlite3, json
c = sqlite3.connect('/data/akhbot.db')
wm = sum(1 for (fs,) in c.execute('SELECT fetch_state FROM sources') if (json.loads(fs or '{}').get('watermark')))
print('PASS watermarked=%d' % wm)" 2>/dev/null || echo ERR)
ck "source checkpoints" "$WM"

LEDGER=$(docker exec akhbot-app python -c "
import sqlite3
c = sqlite3.connect('/data/akhbot.db')
sent = c.execute(\"SELECT COUNT(*) FROM publications WHERE status='SENT'\").fetchone()[0]
mapped = c.execute(\"SELECT COUNT(*) FROM publications WHERE status='SENT' AND remote_id IS NOT NULL\").fetchone()[0]
print('PASS sent=%d mapped=%d' % (sent, mapped) if sent == mapped or sent == 0 else 'FAIL unmapped=' + str(sent-mapped))" 2>/dev/null || echo ERR)
ck "publication ledger" "$LEDGER"

BRAND=$(docker exec akhbot-app python -c "
import os; print('PASS status=' + ('DECIDED' if open('/srv/config/brand.yml').read().count('DECIDED') else 'UNDECIDED'))" 2>/dev/null || echo ERR)
ck "brand config" "$BRAND"

TG=$(docker exec -i akhbot-app python -c "
import os, sys; sys.path.insert(0,'/srv')
from app.config import Settings
s = Settings()
t = s.telegram_publish_target
print('PASS type-pending-validate' if t and not t.startswith('55') else 'FAIL: publish target missing/private?')" 2>/dev/null || echo ERR)
ck "telegram publish target" "$TG"

AI=$(docker exec akhbot-app python -c "
import os
print('PASS deterministic-mode (keys absent = OK)' if not os.environ.get('GLM_API_KEY') else 'PASS provider configured')" 2>/dev/null || echo ERR)
ck "ai optional mode" "$AI"

HB=$(docker exec -i akhbot-app python -c "
import sqlite3, datetime
c = sqlite3.connect('/data/akhbot.db')
keys = [r[0] for r in c.execute(\"SELECT key FROM settings WHERE key LIKE '%_last_run'\")]
need = {'ingest_last_run','pipeline_last_run','soak_last_run'}
print('PASS ' + str(len(keys)) if need <= set(keys) else 'FAIL missing=' + str(sorted(need - set(keys))))" 2>/dev/null || echo ERR)
ck "worker heartbeats" "$HB"

HC=$(docker inspect --format '{{.State.Health.Status}}' akhbot-app 2>/dev/null || echo missing)
ck "docker health" "$([ "$HC" = "healthy" ] && echo PASS || echo "$HC")"

DISK=$(df / | awk 'NR==2{print $5}' | tr -d '%')
ck "disk" "$([ "$DISK" -lt 85 ] && echo "PASS ${DISK}%" || echo "CRITICAL ${DISK}%")"

AUT=$(docker exec akhbot-app python -c "
import sqlite3
c = sqlite3.connect('/data/akhbot.db')
ok = c.execute(\"SELECT COUNT(*) FROM settings WHERE key='SOAK_TEST_STARTED_AT'\").fetchone()[0]
print('PASS' if ok else 'WARN no-soak-marker')" 2>/dev/null || echo ERR)
ck "autonomous mode markers" "$AUT"

exit $fail
