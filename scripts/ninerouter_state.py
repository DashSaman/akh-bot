import json
import sqlite3
import sys

db = sqlite3.connect("/opt/akhbot/9router-data/db/data.sqlite")
db.row_factory = sqlite3.Row

print("== connections ==")
for r in db.execute("SELECT provider, name, isActive, data FROM providerConnections ORDER BY createdAt"):
    d = json.loads(r["data"])
    k = d.get("apiKey") or ""
    print(r["provider"][:44], "|", r["name"], "| active=", r["isActive"],
          "| key=", (k[:4] + "…" if k else "-"), "| test=", d.get("testStatus"))

print("== combos ==")
for r in db.execute("SELECT name, kind, models FROM combos"):
    print(r["name"], r["kind"], r["models"][:200])

print("== kv keys (model catalogs) ==")
try:
    for r in db.execute("SELECT key, length(value) FROM kv"):
        print(r[0], r[1])
except Exception as e:
    print("kv err", e)

# direct probe: ask 9Router for a sambanova model
key = sys.argv[1] if len(sys.argv) > 1 else ""
if key:
    import httpx
    for model in ["sambanova/DeepSeek-V3.2", "sambanova/Meta-Llama-3.3-70B-Instruct", "sambanova/MiniMax-M2.7"]:
        try:
            r = httpx.post("http://127.0.0.1:20128/v1/chat/completions",
                           headers={"Authorization": "Bearer " + key},
                           json={"model": model, "messages": [{"role": "user", "content": "Reply OK"}],
                                 "max_tokens": 8, "stream": False}, timeout=60)
            body = r.json() if r.status_code == 200 else r.text[:150]
            served = body.get("model", "") if isinstance(body, dict) else ""
            print("PROBE", model, "http=", r.status_code, "served=", served)
        except Exception as e:
            print("PROBE", model, "EXC", str(e)[:100])
