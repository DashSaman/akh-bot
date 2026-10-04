"""6h funnel audit per source: items -> claims -> events -> stories -> holds -> pubs."""
import sqlite3
from datetime import datetime, timedelta, timezone

db = sqlite3.connect("/data/akhbot.db")
db.row_factory = sqlite3.Row
cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S")

print(f"cutoff={cutoff}")
print("identity | platform | state | items6h | claims6h | evs6h | stories6h | HELDnow | pubs6h")

for s in db.execute("SELECT id, identity, platform, endpoint_state FROM sources ORDER BY identity"):
    items = db.execute(
        "SELECT COUNT(*) c FROM raw_items WHERE source_id=? AND fetched_at >= ?", (s["id"], cutoff)
    ).fetchone()["c"]
    evs = db.execute(
        "SELECT COUNT(DISTINCT event_id) n FROM claims WHERE source_item_id IN "
        "(SELECT id FROM raw_items WHERE source_id=? AND fetched_at >= ?)",
        (s["id"], cutoff),
    ).fetchone()["n"]
    claims = db.execute(
        "SELECT COUNT(*) c FROM claims WHERE source_item_id IN "
        "(SELECT id FROM raw_items WHERE source_id=? AND fetched_at >= ?)",
        (s["id"], cutoff),
    ).fetchone()["c"]
    stories = db.execute(
        "SELECT COUNT(*) c FROM stories WHERE event_id IN (SELECT DISTINCT event_id FROM claims "
        "WHERE source_item_id IN (SELECT id FROM raw_items WHERE source_id=?)) AND created_at >= ?",
        (s["id"], cutoff),
    ).fetchone()["c"]
    held = db.execute(
        "SELECT COUNT(*) c FROM events WHERE status='HELD' AND id IN (SELECT DISTINCT event_id FROM claims "
        "WHERE source_item_id IN (SELECT id FROM raw_items WHERE source_id=?))",
        (s["id"],),
    ).fetchone()["c"]
    pubs = db.execute(
        "SELECT COUNT(*) c FROM publications WHERE story_id IN (SELECT id FROM stories WHERE event_id IN "
        "(SELECT DISTINCT event_id FROM claims WHERE source_item_id IN "
        "(SELECT id FROM raw_items WHERE source_id=?))) AND created_at >= ?",
        (s["id"], cutoff),
    ).fetchone()["c"]
    if items or evs or pubs:
        print(f"{s['identity']} | {s['platform']} | {s['endpoint_state']} | {items} | {claims} | {evs} | {stories} | {held} | {pubs}")

print("\n== events by status (6h) ==")
for r in db.execute("SELECT status, COUNT(*) c FROM events WHERE first_seen_at >= ? GROUP BY status", (cutoff,)):
    print(" ", r["status"], r["c"])
print("== stories by status (6h) ==")
for r in db.execute("SELECT status, COUNT(*) c FROM stories WHERE created_at >= ? GROUP BY status", (cutoff,)):
    print(" ", r["status"], r["c"])
print("== recent publications by story/event (6h) ==")
for r in db.execute(
    "SELECT p.id, p.status, p.created_at, st.lifecycle, substr(st.headline,1,50) h FROM publications p "
    "JOIN stories st ON st.id=p.story_id WHERE p.created_at >= ? ORDER BY p.id DESC LIMIT 8", (cutoff,)
):
    print(" ", r["id"], r["status"], r["created_at"][:16], r["lifecycle"], "|", r["h"])
