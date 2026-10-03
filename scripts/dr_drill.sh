#!/usr/bin/env bash
# PART-9 DR drill — FULL production-like backup -> restore -> verify, in an
# ISOLATED Rasteh-owned container/volume (never over the live DB). Proves
# restorability of every canonical table + watermarks + ledger mappings, then
# boots the app against the restored DB. Usage: dr_drill.sh <backup.db>
set -euo pipefail
BACKUP="${1:?usage: dr_drill.sh <backup.db>}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
VOL="akhbot_dr_${STAMP}"

echo "== DR DRILL ${STAMP}: isolated restore of ${BACKUP}"
docker volume create "${VOL}" >/dev/null

# 1) restore INTO THE ISOLATED VOLUME (live volume untouched)
docker run --rm -v "${VOL}:/data" -v "$(dirname "${BACKUP}"):/bk:ro" \
  alpine:3.20 sh -c "cp /bk/$(basename "${BACKUP}") /data/akhbot.db && chmod -R 777 /data && ls -la /data"

# 2) verify every canonical table restored + migrations no-op
docker run --rm -v "${VOL}:/data" -v /opt/akhbot/app/scripts:/hostscripts:ro \
  -e PYTHONPATH=/srv -w /srv --entrypoint python akhbot-app:latest \
  /hostscripts/dr_verify.py /data/akhbot.db

# 3) boot the app against the restored DB (restart-after-restore proof)
docker run -d --name "akhbot-dr-${STAMP}" \
  -v "${VOL}:/data" -e DATA_DIR=/data -e WORKERS_ENABLED=false \
  -e EVENT_ENGINE_V2_ENABLED=true \
  -e ADMIN_USERNAME=dr -e ADMIN_PASSWORD=dr-only-local \
  -e SESSION_SECRET=dr-local-secret \
  -p 127.0.0.1:18307:8000 akhbot-app:latest >/dev/null
sleep 6
curl -fsS http://127.0.0.1:18307/health && echo " -> DR instance healthy on :18307"
curl -fsS "http://127.0.0.1:18307/latest" >/dev/null && echo " -> public pages render from restored data"

# 4) cleanup isolated resources (live untouched)
docker rm -f "akhbot-dr-${STAMP}" >/dev/null
docker volume rm "${VOL}" >/dev/null
echo "== DR DRILL ${STAMP}: PASS (isolated volume + container removed)"
