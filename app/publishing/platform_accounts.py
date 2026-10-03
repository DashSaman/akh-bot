"""PART-8 — CORE-009 PlatformAccount: per-platform config/health registry.

Each platform (telegram / x / instagram / threads / facebook / web) is
independently configurable: enabled, account id, auth state, health, last
publish, last error. Failure of one platform NEVER blocks others —
distribution_plan() only includes platforms whose account is enabled and
whose adapter exists; a platform without legitimate API access stays
BLOCKED_EXTERNAL with a truthful auth state (no fake adapters, no scraping).
"""
from __future__ import annotations

from typing import Any

from app.db.database import Database
from app.db.repo import utcnow

PLATFORMS = ("telegram", "x", "instagram", "threads", "facebook", "web")

# truthful default auth states per platform (PART-8 §19/§20)
_DEFAULT_AUTH = {
    "telegram": "CONFIGURED",      # live when env token+chat present
    "x": "BLOCKED_EXTERNAL",       # paid API — BLOCKED_BY_COST_POLICY
    "instagram": "AUTH_REQUIRED",  # Meta OAuth consent (owner)
    "threads": "AUTH_REQUIRED",
    "facebook": "AUTH_REQUIRED",
    "web": "CONFIGURED",           # website pages live (PREVIEW until domain)
}


def ensure_defaults(db: Database) -> None:
    """Idempotent seed of one account row per known platform."""
    for name in PLATFORMS:
        db.execute(
            "INSERT OR IGNORE INTO platform_accounts(platform, account_id,"
            " enabled, auth_state, health, created_at, updated_at)"
            " VALUES(?,?,0,?,'UNKNOWN',?,?)",
            (name, "", _DEFAULT_AUTH.get(name, "NOT_CONFIGURED"),
             utcnow(), utcnow()))


def get(db: Database, platform: str) -> dict[str, Any] | None:
    return db.query_one(
        "SELECT * FROM platform_accounts WHERE platform=?", (platform,))


def accounts(db: Database) -> list[dict[str, Any]]:
    ensure_defaults(db)
    return [dict(r) for r in db.query(
        "SELECT * FROM platform_accounts ORDER BY platform")]


def set_state(db: Database, platform: str, *, enabled: bool | None = None,
              auth_state: str | None = None, health: str | None = None,
              account_id: str | None = None, last_error: str | None = None) -> None:
    sets, params = [], []
    if enabled is not None:
        sets.append("enabled=?"); params.append(1 if enabled else 0)
    if auth_state is not None:
        sets.append("auth_state=?"); params.append(auth_state)
    if health is not None:
        sets.append("health=?"); params.append(health)
    if account_id is not None:
        sets.append("account_id=?"); params.append(account_id)
    if last_error is not None:
        sets.append("last_error=?"); params.append(last_error[:200])
    if not sets:
        return
    sets.append("updated_at=?"); params.append(utcnow())
    params.append(platform)
    db.execute(f"UPDATE platform_accounts SET {', '.join(sets)} WHERE platform=?", params)


def mark_published(db: Database, platform: str) -> None:
    db.execute("UPDATE platform_accounts SET last_publish_at=?, health='HEALTHY',"
               " updated_at=? WHERE platform=?", (utcnow(), utcnow(), platform))


def mark_error(db: Database, platform: str, error: str) -> None:
    db.execute("UPDATE platform_accounts SET last_error=?, health='ERROR',"
               " updated_at=? WHERE platform=?", (error[:200], utcnow(), platform))


def active_publish_platforms(db: Database) -> list[str]:
    """Platforms currently enabled AND legitimately authenticated."""
    return [r["platform"] for r in db.query(
        "SELECT platform FROM platform_accounts WHERE enabled=1"
        " AND auth_state IN ('CONFIGURED','OK')")]
