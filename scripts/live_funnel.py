"""Live funnel snapshot: events/stories/jobs + translation evidence (read-only)."""
import datetime
import json
import sqlite3
from collections import Counter

db = sqlite3.connect("/data/akhbot.db")
db.row_factory = sqlite3.Row


def q(sql, args=()):
    return [dict(r) for r in db.execute(sql, args).fetchall()]


def parse(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00").replace(" ", "T")
    try:
        d = datetime.datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


now = datetime.datetime.now(datetime.timezone.utc)
ecols = [r[1] for r in db.execute("PRAGMA table_info(events)").fetchall()]
when = "created_at" if "created_at" in ecols else "first_seen_at"
rows = q(f"SELECT id,status,verification,{when} created_at FROM events ORDER BY id DESC LIMIT 60")
print("recent60 events:", Counter(r["status"] for r in rows))

st = q("SELECT id,event_id,lifecycle,created_at,published_at,headline FROM stories ORDER BY id DESC LIMIT 40")
recent = [s for s in st if parse(s["created_at"])
          and (now - parse(s["created_at"])).total_seconds() < 6 * 3600]
print("stories last6h:", len(recent))
for s in recent[:12]:
    print("  story", s["id"], s["lifecycle"], (s["headline"] or "")[:60])

print("jobs:", json.dumps(q(
    "SELECT job_type,status,COUNT(*) c FROM jobs GROUP BY job_type,status"), default=str))

pub = q("SELECT job_type,status,dedupe_key,created_at,finished_at,last_error "
        "FROM jobs WHERE job_type LIKE 'publish%' ORDER BY id DESC LIMIT 12")
for j in pub:
    print("pub:", j["job_type"], j["status"], (j["created_at"] or "")[:19],
          (j["last_error"] or "")[:60])

# translation activity: llm_cache growth + NEEDS_LANGUAGE holds
try:
    lc = q("SELECT COUNT(*) c, MAX(created_at) m FROM llm_cache")
    print("llm_cache:", lc)
except Exception as ex:
    print("llm_cache err:", ex)
held = q(f"SELECT id,verification,{when} updated_at FROM events WHERE status='HELD' ORDER BY id DESC LIMIT 8")
for h in held:
    print("held:", h["id"], (h["reason"] or "")[:40], (h["updated_at"] or "")[:19])
