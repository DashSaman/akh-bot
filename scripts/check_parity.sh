#!/usr/bin/env bash
# Deployment parity check: docker run (production) vs docker-compose.yml (portable).
# Verifies port/env/volume/network/restart/logging/healthcheck stay equivalent.
# Run on the server: bash /opt/akhbot/app/scripts/check_parity.sh
set -uo pipefail
APP=/opt/akhbot/app

fail=0
check() { # name expected actual
  if [ "$2" = "$3" ]; then
    printf 'PASS  %-28s %s\n' "$1" "$3"
  else
    printf 'FAIL  %-28s expected=%s actual=%s\n' "$1" "$2" "$3"
    fail=1
  fi
}

INSPECT=$(docker inspect akhbot-app 2>/dev/null) || { echo "container missing"; exit 1; }
jq_get() { echo "$INSPECT" | python3 -c "
import json,sys
d = json.load(sys.stdin)[0]
try:
    print(eval(sys.argv[1]))
except Exception:
    print('?')
" "$1"; }

PORTS=$(jq_get "d['NetworkSettings']['Ports'].get('8000/tcp',[{}])[0].get('HostIp','?')+':'+d['NetworkSettings']['Ports'].get('8000/tcp',[{}])[0].get('HostPort','?')")
check "port binding" "127.0.0.1:8307" "$PORTS"

RESTART=$(jq_get "d['HostConfig']['RestartPolicy']['Name']")
check "restart policy" "unless-stopped" "$RESTART"

NETS=$(jq_get "','.join(sorted(d['NetworkSettings']['Networks'].keys()))")
check "network" "akhbot_internal" "$NETS"

VOLS=$(jq_get "';'.join(m['Name']+':'+m['Destination'] for m in d['Mounts'])")
check "volume" "akhbot_data:/data" "$VOLS"

LOGD=$(jq_get "d['HostConfig']['LogConfig'].get('Type') or d['HostConfig']['LogConfig'].get('Driver')")
LOGM=$(jq_get "d['HostConfig']['LogConfig']['Config'].get('max-size','?')")
LOGF=$(jq_get "d['HostConfig']['LogConfig']['Config'].get('max-file','?')")
check "log driver" "json-file" "$LOGD"
check "log max-size" "10m" "$LOGM"
check "log max-file" "3" "$LOGF"

HC=$(jq_get "d['Config']['Healthcheck']['Test'] is not None")
check "healthcheck present" "True" "$HC"

DATA_DIR=$(docker exec akhbot-app printenv DATA_DIR)
check "DATA_DIR env" "/data" "$DATA_DIR"

# compose file side (portable source of truth)
CP_PORT=$(python3 -c "
import yaml
c = yaml.safe_load(open('$APP/docker-compose.yml'))
s = c['services']['app']
print(s['ports'][0])
")
check "compose port equals prod" "127.0.0.1:8307:8000" "$CP_PORT"
CP_VOL=$(python3 -c "
import yaml
c = yaml.safe_load(open('$APP/docker-compose.yml'))
print(c['volumes'] and 'akhbot_data' in c['volumes'])
")
check "compose volume defined" "True" "$CP_VOL"

exit $fail
