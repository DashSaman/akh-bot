#!/usr/bin/env bash
# akh-bot deployment on the Hetzner host (uses docker run: host has no compose plugin).
# Safe-by-design: creates only akhbot-* resources; never touches other projects.
# Usage: sudo bash scripts/deploy.sh   (run from the repo checkout at /opt/akhbot/app)
set -euo pipefail

APP_DIR="${AKH_DIR:-/opt/akhbot}"
PORT="${AKH_PORT:-8307}"
IMAGE="akhbot-app:latest"
NET="akhbot_internal"
 VOL="akhbot_data"

cd "$APP_DIR/app"

[ -f "$APP_DIR/.env" ] || { echo "missing $APP_DIR/.env (copy .env.example)"; exit 1; }
cp -f config/brand.example.yml config/brand.yml 2>/dev/null || true

docker build -t "$IMAGE" .

docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET"

# replace container if present (additive; other projects untouched)
docker rm -f akhbot-app 2>/dev/null || true

docker run -d \
  --name akhbot-app \
  --restart unless-stopped \
  --init \
  --network "$NET" \
  -p "127.0.0.1:${PORT}:8000" \
  --env-file "$APP_DIR/.env" \
  -e DATA_DIR=/data \
  -v "$VOL:/data" \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
  --health-cmd "python -c \"import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)\"" \
  --health-interval 30s --health-timeout 5s --health-retries 3 \
  "$IMAGE"

sleep 3
docker ps --filter name=akhbot-app --format '{{.Names}} {{.Status}}'
curl -fsS "http://127.0.0.1:${PORT}/health" && echo " -> healthy"
