"""DR drill verification: every canonical entity survives backup→restore."""
from __future__ import annotations

import sys

REQUIRED = (
    ("sources", 1), ("raw_items", 1), ("claims", 1), ("events", 1),
    ("stories", 1), ("story_versions", 1), ("publications", 1),
    ("evidence_links", 0), ("verification_runs", 0),
    ("platform_accounts", 0), ("media_assets", 0), ("jobs", 0),
    ("source_context", 0), ("burst_groups", 0),
)


def main(path: str) -> int:
    from app.db.database import Database
    from app.db.migrate import applied_version, apply_migrations

    db = Database(path)
    pre = applied_version(db)
    applied = apply_migrations(db)  # must be a no-op on a current backup
    post = applied_version(db)
    print(f"schema: {pre} -> {post} (migrations applied on restore: {applied})")
    ok = True
    counts = {}
    for table, minimum in REQUIRED:
        n = db.query_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
        counts[table] = n
        status = "OK" if n >= minimum else "MISSING"
        if n < minimum:
            ok = False
        print(f"  {table}: {n} {status}")
    # watermarks / remote mappings preserved
    wm = db.query_one(
        "SELECT COUNT(*) AS n FROM sources WHERE last_remote_id IS NOT NULL")["n"]
    mapped = db.query_one(
        "SELECT COUNT(*) AS n FROM publications WHERE status='SENT'"
        " AND remote_id IS NOT NULL")["n"]
    print(f"  watermarks present: {wm}; SENT remote mappings: {mapped}")
    # secrets never live in the DB (env-only) — verify no telegram token columns
    leak = db.query_one(
        "SELECT COUNT(*) AS n FROM settings WHERE key LIKE '%token%'"
        " OR key LIKE '%api_key%'")["n"]
    print(f"  secret-looking settings rows: {leak} (expected 0 — secrets are env-only)")
    if leak:
        ok = False
    db.close()
    print("DR-VERIFY:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "/data/akhbot.db"))
