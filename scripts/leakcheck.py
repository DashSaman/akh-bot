import json
import sqlite3

db = sqlite3.connect("/data/akhbot.db")
db.row_factory = sqlite3.Row
scols = [r[1] for r in db.execute("PRAGMA table_info(stories)").fetchall()]
print("story cols:", scols)
draft_col = "draft_json" if "draft_json" in scols else "draft"

rows = db.execute(
    f"SELECT s.id, s.{draft_col} d FROM stories s JOIN publications p "
    "ON p.story_id=s.id WHERE p.status='SENT' AND p.platform='telegram' "
    "ORDER BY p.id DESC LIMIT 10").fetchall()
sys = __import__("sys")
sys.path.insert(0, "/srv")
from app.publishing.telegram_bot import is_persian_public_text  # noqa: E402

bad = 0
for r in rows:
    try:
        d = json.loads(r["d"] or "{}")
        txt = ((d.get("platform_variants") or {}).get("telegram", "")
               or d.get("lead", "") or d.get("headline", ""))
    except Exception:
        txt = ""
    ok = is_persian_public_text(txt)
    bad += 0 if ok else 1
    print(r["id"], "PERSIAN" if ok else "FOREIGN!", txt[:60].replace("\n", " / "))
print("foreign_leak_count:", bad)
