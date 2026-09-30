#!/usr/bin/env bash
# akh-bot doctor — server-side health/status snapshot. Prints NO secrets.
# Run on the Hetzner host: bash /opt/akhbot/app/scripts/doctor.sh
# Optional drift check: bash scripts/doctor.sh --check-drift  (exits 1 on drift)
set -uo pipefail

APP=/opt/akhbot/app
PORT=8307

line() { printf '%-28s %s\n' "$1" "$2"; }

echo "=== akhbot doctor ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="

REPO_HEAD=$(git -C "$APP" rev-parse --short HEAD 2>/dev/null || echo "?")
DEPLOYED_HEAD=$(docker exec akhbot-app printenv AKHBOT_GIT_SHA 2>/dev/null || echo "?")
line "repository HEAD" "$REPO_HEAD"
line "deployed HEAD (image)" "$DEPLOYED_HEAD"

HEALTH=$(docker inspect --format '{{.State.Health.Status}}' akhbot-app 2>/dev/null || echo "missing")
RESTART=$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' akhbot-app 2>/dev/null || echo "?")
line "container health" "akhbot-app: $HEALTH (restart=$RESTART)"

PORT_STATE=$(ss -lnt | grep -q "127.0.0.1:$PORT " && echo "127.0.0.1:$PORT (localhost-only)" || echo "NOT LISTENING")
line "port" "$PORT_STATE"

MEM=$(docker stats --no-stream --format '{{.MemUsage}} ({{.CPUPerc}} CPU)' akhbot-app 2>/dev/null)
line "container RAM/CPU" "${MEM:-?}"
line "host RAM" "$(free -h | awk 'NR==2{print $3 " used / " $7 " available"}')"
line "host disk /" "$(df -h / | awk 'NR==2{print $3 " used / " $4 " free (" $5 ")"}')"

READY=$(curl -fsS "http://127.0.0.1:$PORT/ready" 2>/dev/null || echo '{}')
for kv in llm telegram_publish telegram_ingest workers brand_status preview_mode; do
  val=$(echo "$READY" | python3 -c "import json,sys; print(json.load(sys.stdin).get('$kv','?'))" 2>/dev/null || echo "?")
  line "$kv" "$val"
done

RSS=$(docker exec akhbot-app python -c "
import sqlite3
c = sqlite3.connect('/data/akhbot.db')
src = c.execute(\"SELECT COUNT(*) FROM sources WHERE status='APPROVED'\").fetchone()[0]
last = c.execute(\"SELECT MAX(last_success_at) FROM sources\").fetchone()[0] or 'never'
items = c.execute('SELECT COUNT(*) FROM raw_items').fetchone()[0]
print(f'approved={src} items={items} last_success={last}')
" 2>/dev/null || echo "db-unreachable")
line "RSS collector" "$RSS"

PAUSE=$(docker exec akhbot-app python -c "
import sqlite3
c = sqlite3.connect('/data/akhbot.db')
v = c.execute(\"SELECT value FROM settings WHERE key='pause_all'\").fetchone()
print('PAUSED' if v and v[0]=='1' else 'ACTIVE')
" 2>/dev/null || echo "?")
line "publishing pause" "$PAUSE"

GLM_SET=$(grep -cE '^GLM_API_KEY=.+' /opt/akhbot/.env 2>/dev/null || echo 0)
TG_SET=$(grep -cE '^TELEGRAM_BOT_TOKEN=.+|^TELEGRAM_STAGING_CHAT_ID=.+' /opt/akhbot/.env 2>/dev/null || echo 0)
line "GLM key in .env" "$([ "$GLM_SET" -ge 1 ] && echo YES || echo NO)"
line "Telegram pub creds in .env" "$([ "$TG_SET" -ge 2 ] && echo YES || echo NO)"
line "public base URL" "$(grep -E '^PUBLIC_BASE_URL=.+' /opt/akhbot/.env | sed 's/PUBLIC_BASE_URL=//' | grep . || echo '(empty → preview/noindex)')"

if [ "${1:-}" = "--check-drift" ]; then
  if [ "$REPO_HEAD" != "$DEPLOYED_HEAD" ]; then
    echo "DRIFT: repository $REPO_HEAD != deployed $DEPLOYED_HEAD"
    exit 1
  fi
  echo "OK: repository and deployed HEAD match ($REPO_HEAD)"
fi
