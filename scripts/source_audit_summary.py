"""Compact audit view: blocked identities + active-but-zero-item endpoints."""
import datetime
import json
import sqlite3

db = sqlite3.connect("/data/akhbot.db")
db.row_factory = sqlite3.Row
NOW = datetime.datetime.now(datetime.timezone.utc)
t24 = (NOW - datetime.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")

out = {"blocked": [], "zero24": []}
for s in db.execute(
        "SELECT id,name,platform,identity,endpoint_state,notes,url FROM sources"):
    ident = s["identity"] or s["name"]
    if s["endpoint_state"] == "ACTIVE":
        c = db.execute(
            "SELECT COUNT(*) c, MAX(fetched_at) m FROM raw_items "
            "WHERE source_id=? AND fetched_at >= ?", (s["id"], t24)).fetchone()
        if c["c"] == 0:
            out["zero24"].append({
                "identity": ident, "name": s["name"][:40],
                "platform": s["platform"], "url": (s["url"] or "")[:60],
                "note": (s["notes"] or "")[-40:]})
    else:
        out["blocked"].append({
            "identity": ident, "platform": s["platform"],
            "state": s["endpoint_state"],
            "url": (s["url"] or "")[:50],
            "note": (s["notes"] or "")[-50:]})
print(json.dumps(out, ensure_ascii=False, indent=1)[:40000])
