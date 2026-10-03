"""Live 9Router combo test (runs INSIDE akhbot-app container).

Usage: docker exec -e NR_KEY=... akhbot-app python /tmp/ninerouter_combo_test.py [model]
Prints which model answered + content head. Never prints the key.
"""
import json
import os
import sys
import urllib.request

MODEL = sys.argv[1] if len(sys.argv) > 1 else "rasteh-translate"
URL = "http://nine-router:20128/v1/chat/completions"

payload = {
    "model": MODEL,
    "messages": [{"role": "user",
                  "content": 'Reply with JSON only: {"ok": true}'}],
    "max_tokens": 80,
}
req = urllib.request.Request(
    URL, data=json.dumps(payload).encode(),
    headers={"Authorization": "Bearer " + os.environ.get("NR_KEY", ""),
             "Content-Type": "application/json"})
try:
    resp = urllib.request.urlopen(req, timeout=120)
    raw = resp.read().decode("utf-8", "replace")
    # tolerate SSE/extra data: parse the FIRST JSON object only
    dec = json.JSONDecoder()
    obj, _ = dec.raw_decode(raw.lstrip())
    ch = (obj.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    print("HTTP", resp.status, "MODEL:", obj.get("model"))
    print("CONTENT:", str(msg.get("content"))[:150])
except Exception as ex:  # noqa: BLE001
    print("ERR:", str(ex)[:250])
