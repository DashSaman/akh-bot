"""URGENT diagnostic — exact live publication funnel (windows: 30m/1h/3h/6h)."""
from __future__ import annotations

import sys

from app.db.database import Database

WINDOWS = [("30m", "-30 minutes"), ("1h", "-60 minutes"),
           ("3h", "-180 minutes"), ("6h", "-360 minutes")]


def main(path: str) -> int:
    db = Database(path)
    q = lambda s, p=(): db.query_one(s, p)  # noqa: E731

    print("=" * 70)
    print("A) RAWITEMS FUNNEL")
    for label, since in WINDOWS:
        total = q(f"SELECT COUNT(*) AS n FROM raw_items WHERE fetched_at >= datetime('now','{since}')")["n"]
        ok = q(f"SELECT COUNT(*) AS n FROM raw_items WHERE fetched_at >= datetime('now','{since}') AND activation_ok=1")["n"]
        backfill = total - ok
        new_state = q(f"SELECT COUNT(*) AS n FROM raw_items WHERE fetched_at >= datetime('now','{since}') AND processed_state='NEW'")["n"]
        print(f"  [{label}] total={total} activation_ok={ok} backfill(activation_ok=0)={backfill} NEW-state={new_state}")

    print("\n  by language (1h):")
    for r in db.query("SELECT language, activation_ok, COUNT(*) AS c FROM raw_items"
                      " WHERE fetched_at >= datetime('now','-60 minutes')"
                      " GROUP BY language, activation_ok ORDER BY c DESC LIMIT 12"):
        print(f"    {r['language'] or 'und'} activation_ok={r['activation_ok']}: {r['c']}")

    print("\n  by source (1h, top 12):")
    for r in db.query("SELECT s.name, s.identity, r.activation_ok AS ok, COUNT(*) AS c"
                      " FROM raw_items r JOIN sources s ON s.id=r.source_id"
                      " WHERE r.fetched_at >= datetime('now','-60 minutes')"
                      " GROUP BY s.name, s.identity, r.activation_ok ORDER BY c DESC LIMIT 12"):
        print(f"    {r['name']} ({r['identity']}) ok={r['ok']}: {r['c']}")

    print("\nB) CLAIMS (1h):")
    for r in db.query("SELECT state, COUNT(*) AS c FROM claims"
                      " WHERE created_at >= datetime('now','-60 minutes') GROUP BY state"):
        print(f"    {r['state']}: {r['c']}")
    print("  claims total by state (all time):")
    for r in db.query("SELECT state, COUNT(*) AS c FROM claims GROUP BY state"):
        print(f"    {r['state']}: {r['c']}")

    print("\nC) EVENTS (1h):")
    print("  status:", [dict(r) for r in db.query(
        "SELECT status, COUNT(*) AS c FROM events WHERE last_seen_at >= datetime('now','-60 minutes')"
        " GROUP BY status")])
    print("  verification:", [dict(r) for r in db.query(
        "SELECT verification, COUNT(*) AS c FROM events WHERE last_seen_at >= datetime('now','-60 minutes')"
        " GROUP BY verification")])

    print("\nD) STORIES (1h):")
    for r in db.query("SELECT status, lifecycle, COUNT(*) AS c FROM stories"
                      " WHERE created_at >= datetime('now','-60 minutes')"
                      " GROUP BY status, lifecycle"):
        print(f"    {r['status']}/{r['lifecycle']}: {r['c']}")

    print("\nE) JOBS (publication, all time by status):")
    for r in db.query("SELECT job_type, status, COUNT(*) AS c FROM jobs"
                      " WHERE job_type LIKE 'publish%' GROUP BY job_type, status"):
        print(f"    {r['job_type']}/{r['status']}: {r['c']}")
    print("  failed publication jobs by error (last 6h):")
    for r in db.query("SELECT job_type, last_error, COUNT(*) AS c FROM jobs"
                      " WHERE job_type LIKE 'publish%' AND status='failed'"
                      " AND updated_at >= datetime('now','-6 hours')"
                      " GROUP BY job_type, last_error ORDER BY c DESC LIMIT 10"):
        print(f"    {r['job_type']} | {(r['last_error'] or '')[:70]}: {r['c']}")

    print("\nF) PUBLICATIONS by status:")
    for r in db.query("SELECT status, COUNT(*) AS c FROM publications GROUP BY status"):
        print(f"    {r['status']}: {r['c']}")
    print("  SKIPPED by error (last 6h):")
    for r in db.query("SELECT error, COUNT(*) AS c FROM publications"
                      " WHERE status='SKIPPED' AND updated_at >= datetime('now','-6 hours')"
                      " GROUP BY error ORDER BY c DESC LIMIT 10"):
        print(f"    {(r['error'] or '')[:60]}: {r['c']}")

    print("\nG) TIMELINE TRUTH:")
    last_sent = q("SELECT updated_at AS t, remote_id, story_id FROM publications"
                  " WHERE status='SENT' AND remote_id IS NOT NULL"
                  " ORDER BY id DESC LIMIT 1")
    print(f"  LAST SENT: {dict(last_sent) if last_sent else None}")
    last_story = q("SELECT id, headline, created_at FROM stories ORDER BY id DESC LIMIT 1")
    print(f"  LAST STORY: id={last_story['id']} at={last_story['created_at']} | {last_story['headline'][:60]}")
    last_job = q("SELECT id, job_type, status, created_at FROM jobs WHERE job_type LIKE 'publish%' ORDER BY id DESC LIMIT 1")
    print(f"  LAST PUB JOB: {dict(last_job) if last_job else None}")

    print("\nH) RATE CAPS (live):")
    for label, since, cap_col in (("1h", "-60 minutes", "max_posts_per_hour"),
                                  ("24h", "-1440 minutes", "max_posts_per_day")):
        n = q(f"SELECT COUNT(*) AS n FROM publications WHERE status='SENT'"
              f" AND updated_at >= datetime('now','{since}')")["n"]
        print(f"    SENT {label}: {n}")

    print("\nI) SENT last 12 (timestamps):")
    for r in db.query("SELECT id, story_id, remote_id, updated_at FROM publications"
                      " WHERE status='SENT' ORDER BY id DESC LIMIT 12"):
        print(f"    pub#{r['id']} story={r['story_id']} remote={r['remote_id']} at={r['updated_at']}")

    print("\nJ) HELD events by verification (all):")
    for r in db.query("SELECT verification, COUNT(*) AS c FROM events WHERE status='HELD' GROUP BY verification"):
        print(f"    {r['verification']}: {r['c']}")

    print("\nK) pipeline hold markers in logs — check docker logs separately")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "/data/akhbot.db"))
