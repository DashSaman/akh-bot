import sqlite3

db = sqlite3.connect("/data/akhbot.db")
q = """
UPDATE publications SET status='SKIPPED',
  error='orphaned: event already SENT elsewhere (cleanup 2026-10-04)'
 WHERE status='PENDING' AND story_id IN (
   SELECT st.id FROM stories st WHERE st.event_id IN (
     SELECT st2.event_id FROM stories st2 JOIN publications p2 ON p2.story_id=st2.id
     WHERE p2.status='SENT'))
"""
cur = db.execute(q)
db.commit()
print("cleaned=", cur.rowcount)
for r in db.execute("SELECT status, COUNT(*) c FROM publications GROUP BY status"):
    print(r[0], r[1])
