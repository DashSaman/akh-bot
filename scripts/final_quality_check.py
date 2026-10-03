from app.db.database import Database
import datetime

db = Database('/data/akhbot.db')
q = lambda s: db.query_one(s)
now = datetime.datetime.now(datetime.UTC)

for k in ("ingest_last_run", "pipeline_last_run", "reverify_last_run", "watchdog_last_run"):
    r = q("SELECT value AS v FROM settings WHERE key='%s'" % k)
    print(k, "age_s:", round((now - datetime.datetime.fromisoformat(r["v"])).total_seconds()))

print("SENT:", q("SELECT COUNT(*) AS n FROM publications WHERE status='SENT'")["n"])
print("raw total:", q("SELECT COUNT(*) AS n FROM raw_items")["n"])
print("raw last10m:", q("SELECT COUNT(*) AS n FROM raw_items WHERE fetched_at >= datetime('now','-10 minutes')")["n"])
print("NEW backlog:", q("SELECT COUNT(*) AS n FROM raw_items WHERE processed_state='NEW'")["n"])
print("orphan eligible>10m:", q("SELECT COUNT(*) AS n FROM raw_items WHERE processed_state='NEW' AND activation_ok=1 AND fetched_at <= datetime('now','-10 minutes')")["n"])
print("dup-SEND violations:", q("SELECT COUNT(*) AS n FROM publications p1 WHERE p1.status='SENT' AND EXISTS (SELECT 1 FROM publications p2 WHERE p2.story_id=p1.story_id AND p2.status='SENT' AND p2.remote_id IS NOT NULL AND p2.remote_id != p1.remote_id AND p2.chat_id = p1.chat_id)")["n"])
print("verification_runs:", q("SELECT COUNT(*) AS n FROM verification_runs")["n"])
print("evidence_links:", q("SELECT COUNT(*) AS n FROM evidence_links")["n"])
print("sources active:", q("SELECT COUNT(*) AS n FROM sources WHERE endpoint_state='ACTIVE'")["n"])
print("source errors:", q("SELECT COUNT(*) AS n FROM sources WHERE last_error != ''")["n"])
print("foreign SENT (sample check via jobs):", q("SELECT COUNT(*) AS n FROM jobs WHERE job_type='publish_send'")["n"], "send jobs total")
db.close()
