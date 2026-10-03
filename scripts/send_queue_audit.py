"""Send-queue audit: pending vs done sends, rate-cap drain, dup-SEND check."""
import datetime
import json
import sqlite3

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
jcols = [r[1] for r in db.execute("PRAGMA table_info(jobs)").fetchall()]
print("job cols:", jcols)

pend = q("SELECT * FROM jobs WHERE job_type='publish_send' AND status='pending' "
         "ORDER BY run_after LIMIT 5")
for p in pend:
    print("pend:", {k: str(p[k])[:60] for k in ("id", "story_id", "run_after", "attempts")
                    if k in p})

done = q("SELECT * FROM jobs WHERE job_type='publish_send' AND status='done' "
         "ORDER BY id DESC LIMIT 15")
for d in done:
    ts = parse(d.get("finished_at") or d.get("updated_at") or "")
    print("done:", d.get("story_id"), "at", str(ts)[:19],
          "age_min", round((now - ts).total_seconds() / 60) if ts else "?")

# dup-SEND invariant via publications (story → at most one SENT)
dups = q("SELECT story_id, COUNT(*) c FROM publications "
         "WHERE status='SENT' GROUP BY story_id HAVING c > 1")
print("dup_publications:", dups)

# foreign leak: recent SENT telegram stories must have Persian draft text
leak = q("SELECT s.id, s.draft FROM stories s JOIN publications p ON p.story_id=s.id "
         "WHERE p.status='SENT' AND p.platform='telegram' ORDER BY p.id DESC LIMIT 8")
import json as _json
for l in leak:
    try:
        d = _json.loads(l["draft"] or "{}")
        txt = (d.get("platform_variants") or {}).get("telegram", "") or d.get("lead", "")
    except Exception:
        txt = ""
    print("sent:", l["id"], (txt or "")[:70].replace(chr(10), " / "))

# pending backlog age
allp = q("SELECT COUNT(*) c, MIN(run_after) m FROM jobs "
         "WHERE job_type='publish_send' AND status='pending'")
print("pending_count:", allp[0]["c"], "oldest_run_after:", allp[0]["m"])

# SENT delta last 2h (python window)
recent_done = [d for d in q("SELECT * FROM jobs WHERE job_type='publish_send' "
                            "AND status='done' ORDER BY id DESC LIMIT 40")
               if parse(d.get("finished_at") or d.get("updated_at") or "")
               and (now - parse(d.get("finished_at") or d.get("updated_at"))).total_seconds() < 7200]
print("sents_last2h:", len(recent_done))
