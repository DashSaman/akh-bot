#!/bin/sh
# combo live test from inside the app container (key via env, never printed)
K=$(grep ^OPENAI_COMPAT_API_KEY= /opt/akhbot/.env | cut -d= -f2)
REQ=/tmp/nr_req.json
cat > "$REQ" <<EOF
{"model":"rasteh-translate","messages":[{"role":"user","content":"Reply with JSON only: {\"ok\":true}"}],"max_tokens":60}
EOF
docker exec -e NR_KEY="$K" akhbot-app python -c "
import json, os, urllib.request
req = urllib.request.Request(
    'http://nine-router:20128/v1/chat/completions',
    data=json.dumps({'model': 'rasteh-translate',
                     'messages': [{'role': 'user', 'content': 'Reply with JSON only: {\"ok\": true}'}],
                     'max_tokens': 60}).encode(),
    headers={'Authorization': 'Bearer ' + os.environ['NR_KEY'],
             'Content-Type': 'application/json'})
try:
    raw = urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "replace")
    print("RAWLEN:", len(raw))
    print("HEAD:", raw[:300].replace(chr(10), " "))
except Exception as ex:
    print("ERR:", str(ex)[:200])
"
