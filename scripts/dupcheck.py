import sqlite3

db = sqlite3.connect("/data/akhbot.db")
db.row_factory = sqlite3.Row
for sid in (1058, 1078, 1141, 1142, 1143):
    rows = db.execute(
        "SELECT id,status,remote_id,story_version,created_at FROM publications "
        "WHERE story_id=? ORDER BY id", (sid,)).fetchall()
    print(sid, [(r["id"], r["status"], r["remote_id"], r["story_version"]) for r in rows])

# true duplicate = same story, SENT, DIFFERENT remote_id
bad = db.execute(
    "SELECT story_id, COUNT(DISTINCT remote_id) c FROM publications "
    "WHERE status='SENT' GROUP BY story_id HAVING c > 1").fetchall()
print("true_distinct_remote_dups:", [dict(r) for r in bad])
