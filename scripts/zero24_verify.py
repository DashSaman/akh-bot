"""Verify which ACTIVE sources truly have 0 items in 24h (parsed windows)."""
import datetime
import json
import sqlite3

db = sqlite3.connect("/data/akhbot.db")
db.row_factory = sqlite3.Row
NOW = datetime.datetime.now(datetime.timezone.utc)


def parse(s):
    if not s:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00").replace(" ", "T"))
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


out = []
for s in db.execute("SELECT id,name,identity,platform,url,last_fetch_at,last_error "
                    "FROM sources WHERE endpoint_state='ACTIVE' AND enabled=1"):
    rows = db.execute("SELECT fetched_at FROM raw_items WHERE source_id=? ORDER BY id DESC LIMIT 200",
                      (s["id"],)).fetchall()
    c24 = 0
    last = None
    for r in rows:
        t = parse(r["fetched_at"])
        if t and (NOW - t).total_seconds() < 86400:
            c24 += 1
        if t and (last is None or t > last):
            last = t
    if c24 == 0:
        out.append({"identity": s["identity"] or s["name"], "name": s["name"][:35],
                    "platform": s["platform"],
                    "last_fetch": str(last)[:19] if last else "",
                    "last_error": (s["last_error"] or "")[:60],
                    "url": (s["url"] or "")[:50]})
print(json.dumps(out, ensure_ascii=False, indent=1)[:15000])
print("TOTAL_ZERO24:", len(out))
