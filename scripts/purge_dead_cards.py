"""Purge card asset rows whose files died with the old container layer, so
the pipeline re-registers fresh cards under the persistent volume."""
import os
import sqlite3

db = sqlite3.connect("/data/akhbot.db")
db.row_factory = sqlite3.Row

dead = alive = 0
for r in db.execute("SELECT id, path FROM media_assets WHERE kind='card' AND path != ''").fetchall():
    if os.path.exists(r["path"]):
        alive += 1
    else:
        db.execute("DELETE FROM media_assets WHERE id=?", (r["id"],))
        dead += 1
db.commit()
print(f"cards alive={alive} purged_dead={dead}")
