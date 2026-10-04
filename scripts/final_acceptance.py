import sqlite3

db = sqlite3.connect("/data/akhbot.db")
db.row_factory = sqlite3.Row

for ident in ("IHRNGO", "UNSC"):
    r = db.execute(
        "SELECT COUNT(*) c FROM raw_items ri JOIN sources s ON ri.source_id=s.id "
        "WHERE s.identity=? AND ri.fetched_at >= datetime('now','-1 day')",
        (ident,),
    ).fetchone()
    print(ident, "items_24h=", r["c"])

# footer-only guard: recent story versions must carry a real body, not just the source footer
import json
rows = db.execute(
    "SELECT sv.id, sv.snapshot_json sj FROM story_versions sv "
    "WHERE sv.created_at >= datetime('now','-3 hour') ORDER BY sv.id DESC LIMIT 3"
).fetchall()
for v in rows:
    snap = json.loads(v["sj"] or "{}")
    body = " ".join(str(x) for x in snap.values()).replace("منبع:", "")
    print("storyver", v["id"], "footer_only=", len(body.strip()) < 60)

r = db.execute("SELECT COUNT(*) c FROM media_assets WHERE status='FAILED'").fetchone()
print("media_failed_ever=", r["c"])

# publications sent in last 24h whose send errored
r = db.execute(
    "SELECT COUNT(*) c FROM publications WHERE created_at >= datetime('now','-1 day') "
    "AND status != 'SENT' AND status != 'SUPERSEDED'"
).fetchone()
print("non_sent_pubs_24h=", r["c"])

r = db.execute(
    "SELECT COUNT(*) c FROM publications WHERE created_at >= datetime('now','-1 day') "
    "AND (error IS NOT NULL AND error != '')"
).fetchone()
print("pubs_with_error_24h=", r["c"])
