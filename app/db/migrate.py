"""Ordered SQL migrations from app/db/migrations/. Idempotent; runs at startup."""
from __future__ import annotations

import importlib.resources
import logging
import re

from .database import Database

log = logging.getLogger("akh.migrate")
_MIGRATIONS_RESOURCE = importlib.resources.files("app.db") / "migrations"


def applied_version(db: Database) -> int:
    db.execute(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    row = db.query_one("SELECT value FROM settings WHERE key='schema_version'")
    return int(row["value"]) if row else 0


def apply_migrations(db: Database) -> list[str]:
    res = _MIGRATIONS_RESOURCE
    files = sorted(
        p.name for p in res.iterdir() if re.fullmatch(r"\d{3}_.*\.sql", p.name)
    )
    current = applied_version(db)
    done: list[str] = []
    for name in files:
        version = int(name.split("_", 1)[0])
        if version <= current:
            continue
        sql = (res / name).read_text(encoding="utf-8")
        with db.tx() as conn:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO settings(key,value) VALUES('schema_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(version),),
            )
        done.append(name)
        log.info("migration applied %s", name)
    return done
