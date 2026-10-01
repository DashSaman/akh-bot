"""Source SLA state machine (PART-2 T3): HEALTHY/DEGRADED/STALE/ERROR/DISABLED."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def evaluate_sla(db, source_id: int, now: datetime | None = None,
                 recovery: bool = False) -> str:
    now = now or datetime.now(timezone.utc)
    s = db.query_one(
        "SELECT enabled, polling_interval_seconds, polling_interval_min,"
        " last_check_at, consecutive_failures, source_control_state FROM sources WHERE id=?",
        (source_id,))
    if s is None:
        return "UNKNOWN"
    if not s["enabled"] or s["source_control_state"] == "OWNER_DISABLED":
        return "DISABLED"
    if recovery:
        db.execute("UPDATE sources SET consecutive_failures=0 WHERE id=?", (source_id,))
        db.execute("DELETE FROM settings WHERE key=?", (f"sla_breach:{source_id}",))
        return "HEALTHY"
    interval = int(s["polling_interval_seconds"] or (s["polling_interval_min"] * 60) or 120)
    tol = max(interval * 3, 90)
    last = s["last_check_at"]
    if last:
        try:
            age = (now - datetime.fromisoformat(last)).total_seconds()
        except ValueError:
            age = None
        if age is not None and age > tol * 4:
            db.execute("INSERT INTO settings(key,value) VALUES(?, '1')"
                       " ON CONFLICT(key) DO UPDATE SET value='1'",
                       (f"sla_breach:{source_id}",))
            return "STALE" if s["consecutive_failures"] < 5 else "ERROR"
        if age is not None and age > tol or int(s["consecutive_failures"] or 0) >= 2:
            db.execute("INSERT INTO settings(key,value) VALUES(?, '1')"
                       " ON CONFLICT(key) DO UPDATE SET value='1'",
                       (f"sla_breach:{source_id}",))
            return "DEGRADED"
    return "HEALTHY"


def due_reconcile(db, now: datetime | None = None) -> list[int]:
    """Watchdog helper: breached sources needing immediate reconcile."""
    now = now or datetime.now(timezone.utc)
    out = []
    for r in db.query(
            "SELECT id, last_check_at, polling_interval_seconds FROM sources"
            " WHERE enabled=1 AND source_control_state='OWNER_ENABLED'"):
        interval = int(r["polling_interval_seconds"] or 120)
        try:
            age = (now - datetime.fromisoformat(r["last_check_at"])).total_seconds()
        except (TypeError, ValueError):
            age = 1e9
        if age > max(interval * 3, 90):
            out.append(int(r["id"]))
    return out
