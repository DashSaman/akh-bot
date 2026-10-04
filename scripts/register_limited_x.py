"""Register X / Truth Social endpoints from the XLSX registry truthfully.

No paid X API: these endpoints are stored with status LIMITED_X_ACCESS,
enabled=0 (never polled). Same-identity website/telegram endpoints carry the
live coverage; identity dedup keeps origin counting correct.
"""
import json, re, sqlite3, sys
from datetime import datetime, timezone

data = json.load(open('/hosttmp/xlsx_dump.json'))
rows = data['External Registry'] + data['Fast Social'] + data['People & Reporters']
db = sqlite3.connect('/data/akhbot.db')
prod = db.execute("SELECT url FROM sources").fetchall()
def norm(u):
    return re.sub(r'^https?://(www\.)?', '', (u or '').lower()).rstrip('/')
prod_urls = {norm(p[0]) for p in prod if p[0]}
now = datetime.now(timezone.utc).isoformat(timespec="seconds")
added = skipped = 0
cols = db.execute("PRAGMA table_info(sources)").fetchall()
required = {c[1] for c in cols}
for r in rows:
    plat, url, ent = r.get('Platform',''), r.get('URL',''), r.get('Entity ID','')
    if plat not in ('X', 'Truth Social') or not url:
        continue
    if norm(url) in prod_urls:
        skipped += 1
        continue
    platform = 'x' if plat == 'X' else 'website'
    db.execute(
        "INSERT INTO sources (name, platform, external_id, url, language, category,"
        " source_type, status, enabled, priority, notes, created_at, identity, endpoint_state)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'LIMITED_X_ACCESS', 0, 50,"
        " 'XLSX registry 2026-10-04: no paid X API — monitor via same-identity live endpoints',"
        " ?, ?, 'registered-not-polled')",
        (r.get('Name', ent), platform, ent, url,
         r.get('Language', '') or '', r.get('Group', '') or '',
         'mirror' if 'mirror' in (r.get('Independent?', '') or '').lower() else 'direct',
         now, ent))
    added += 1
db.commit()
print(f"LIMITED_X_ACCESS registered: {added}, already present: {skipped}")
print("platform totals:", dict(db.execute(
    "SELECT platform, COUNT(*) FROM sources GROUP BY platform").fetchall()))
