"""URGENT diag v2 — python-side time windows (immune to mixed timestamp formats)."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from app.db.database import Database


def parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    t = str(ts).strip().replace("Z", "+00:00").replace(" ", "T")
    if "+" not in t and ":" == t[-3:-2]:
        t += "+00:00"
    try:
        dt = datetime.fromisoformat(t)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def main(path: str) -> int:
    db = Database(path)
    now = datetime.now(timezone.utc)
    wins = {"30m": now - timedelta(minutes=30), "1h": now - timedelta(hours=1),
            "3h": now - timedelta(hours=3), "6h": now - timedelta(hours=6)}
    print("now:", now.isoformat())

    items = db.query("SELECT id, source_id, language, activation_ok, processed_state, fetched_at FROM raw_items")
    rows = [(r, parse(r["fetched_at"])) for r in items]
    print(f"\nTOTAL raw_items: {len(rows)}")
    for label, cutoff in wins.items():
        win = [(r, t) for r, t in rows if t and t >= cutoff]
        ok = sum(1 for r, _ in win if r["activation_ok"])
        fa_ok = sum(1 for r, _ in win if r["activation_ok"] and (r["language"] or "").startswith("fa"))
        new_state = sum(1 for r, _ in win if r["processed_state"] == "NEW")
        print(f"[{label}] total={len(win)} ok={ok} fa_ok={fa_ok} NEW-state={new_state}")
    # last item time
    times = sorted((t for _, t in rows if t))
    print("earliest item:", times[0].isoformat() if times else None)
    print("latest item:", times[-1].isoformat() if times else None)

    # fetch activity per minute for last 30 items
    print("\nlast 10 items by time:")
    for r, t in sorted(rows, key=lambda x: x[1] or now)[-10:]:
        print(f"  item#{r['id']} src={r['source_id']} lang={r['language']} ok={r['activation_ok']} at={t}")

    # stories timeline
    stories = db.query("SELECT id, headline, lifecycle, status, created_at FROM stories ORDER BY id")
    st = [(s, parse(s["created_at"])) for s in stories]
    print(f"\nTOTAL stories: {len(st)}; last 6:")
    for s, t in st[-6:]:
        print(f"  story#{s['id']} {s['status']}/{s['lifecycle']} created={t} | {s['headline'][:50]}")

    # SENT publications timeline (python windows)
    pubs = db.query("SELECT id, story_id, remote_id, status, updated_at, error FROM publications WHERE status IN ('SENT','FAILED')")
    ps = [(p, parse(p["updated_at"])) for p in pubs]
    for label, cutoff in wins.items():
        sent = [(p, t) for p, t in ps if p["status"] == "SENT" and t and t >= cutoff]
        print(f"SENT[{label}]: {len(sent)}")
    last = max((t for p, t in ps if p["status"] == "SENT" and t), default=None)
    print("LAST SENT at:", last.isoformat() if last else None)

    # failed publication jobs w/ errors
    print("\nfailed publish jobs (all):")
    for j in db.query("SELECT id, job_type, last_error, attempts, updated_at FROM jobs"
                      " WHERE job_type LIKE 'publish%' AND status='failed' ORDER BY id DESC LIMIT 12"):
        print(f"  job#{j['id']} {j['job_type']} attempts={j['attempts']} at={j['updated_at']} err={(j['last_error'] or '')[:60]}")

    # events created recently with status/reason
    print("\nrecent events (last 1h, python) + status:")
    evs = db.query("SELECT id, status, verification, title, first_seen_at, last_seen_at FROM events ORDER BY id DESC LIMIT 200")
    n1h = 0
    for e in evs:
        t = parse(e["first_seen_at"]) or parse(e["last_seen_at"])
        if t and t >= wins["1h"]:
            n1h += 1
            if n1h <= 12:
                print(f"  ev#{e['id']} {e['status']}/{e['verification']} at={t.isoformat()} | {e['title'][:50]}")
    print(f"  (total new events 1h: {n1h})")

    # yashar fa items recent → what happened?
    print("\nYASHAR recent items (last 1h):")
    ys = db.query("SELECT r.id, r.text, r.activation_ok, r.processed_state, r.fetched_at, r.language"
                  " FROM raw_items r JOIN sources s ON s.id=r.source_id"
                  " WHERE s.name LIKE '%yashar%' ORDER BY r.id DESC LIMIT 40")
    for r in ys:
        t = parse(r["fetched_at"])
        if t and t >= wins["1h"]:
            print(f"  item#{r['id']} ok={r['activation_ok']} {r['processed_state']} lang={r['language']} | {r['text'][:60].replace(chr(10),' / ')}")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "/data/akhbot.db"))
