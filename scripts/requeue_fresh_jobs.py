"""INCIDENT-2026-10-04: requeue ONLY fresh valid publish_send jobs created
today (stories from this morning). No historical replay: jobs tied to stories
created before today stay untouched."""
import json
import sqlite3

db = sqlite3.connect("/data/akhbot.db")
db.row_factory = sqlite3.Row

rows = db.execute(
    "SELECT j.id, j.payload_json FROM jobs j WHERE j.status='pending' "
    "AND j.job_type='publish_send' AND j.created_at >= '2026-10-04' ORDER BY j.id"
).fetchall()

moved = 0
for r in rows:
    payload = json.loads(r["payload_json"])
    story = db.execute("SELECT created_at, status FROM stories WHERE id=?",
                       (payload.get("story_id"),)).fetchone()
    if not story or story["created_at"] < "2026-10-04":
        print("skip (not fresh):", r["id"])
        continue
    db.execute("UPDATE jobs SET run_after=datetime('now'), attempts=0 WHERE id=?", (r["id"],))
    moved += 1

db.commit()
print("requeued_fresh =", moved)
