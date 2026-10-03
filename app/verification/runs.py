"""PART-4 — traceable VerificationRun (CORE-008).

Every verification decision is recorded: who/what triggered it, what was
found (origins/support/contradictions/high-risk), what resulted, and when the
next check is due. No AI dependency — deterministic gates only.

Triggers: NEW_EVIDENCE / SCHEDULED_REVERIFY / CONTRADICTION / DEADLINE / MANUAL.
dedupe_key (UNIQUE) guarantees: no duplicate runs for the same scheduled
attempt, no duplicate runs on replayed evidence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.database import Database
from app.db.repo import utcnow

NEW_EVIDENCE = "NEW_EVIDENCE"
SCHEDULED_REVERIFY = "SCHEDULED_REVERIFY"
CONTRADICTION = "CONTRADICTION"
DEADLINE = "DEADLINE"
MANUAL = "MANUAL"

# unresolved states get the standing 5-minute reverify cadence
REVERIFY_INTERVAL_SECONDS = 300


def record_run(db: Database, *, event_id: int, claim_id: int | None,
               trigger: str, result: str,
               independent_origin_count: int = 0, support_count: int = 0,
               contradiction_count: int = 0, high_risk: bool = False,
               reason_codes: list[str] | None = None,
               next_verify_at: str | None = None,
               dedupe_key: str | None = None,
               next_verify_seconds: int | None = None) -> int | None:
    """Insert one run (idempotent under dedupe_key). Maintains claim-level
    last_verified_at / next_verify_at / verification_attempts bookkeeping."""
    if trigger not in (NEW_EVIDENCE, SCHEDULED_REVERIFY, CONTRADICTION,
                       DEADLINE, MANUAL):
        raise ValueError(f"bad trigger: {trigger}")
    now = utcnow()
    if next_verify_at is None and next_verify_seconds is not None:
        next_verify_at = (datetime.now(timezone.utc)
                          + timedelta(seconds=next_verify_seconds)).isoformat(timespec="seconds")
    cur = db.execute(
        "INSERT OR IGNORE INTO verification_runs(event_id, claim_id, started_at,"
        " completed_at, trigger, result, independent_origin_count, support_count,"
        " contradiction_count, high_risk, reason_codes, next_verify_at, dedupe_key)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (event_id, claim_id, now, now, trigger, result, independent_origin_count,
         support_count, contradiction_count, 1 if high_risk else 0,
         ",".join(reason_codes or []), next_verify_at, dedupe_key))
    row = db.query_one(
        "SELECT id FROM verification_runs WHERE dedupe_key=?", (dedupe_key,)) \
        if dedupe_key else None
    if row:
        run_id = int(row["id"])
    else:
        run_id = int(cur.lastrowid) if cur.lastrowid else None
    if claim_id and run_id:
        db.execute(
            "UPDATE claims SET last_verified_at=?, next_verify_at=?,"
            " verification_attempts=verification_attempts+1 WHERE id=?",
            (now, next_verify_at, claim_id))
    return run_id


def runs_for_event(db: Database, event_id: int, limit: int = 50) -> list[dict]:
    return db.query(
        "SELECT * FROM verification_runs WHERE event_id=?"
        " ORDER BY id DESC LIMIT ?", (event_id, limit))


def runs_for_claim(db: Database, claim_id: int, limit: int = 20) -> list[dict]:
    return db.query(
        "SELECT * FROM verification_runs WHERE claim_id=?"
        " ORDER BY id DESC LIMIT ?", (claim_id, limit))


def due_reverify_slot(now: datetime | None = None) -> str:
    """Standing 5-minute slot id — one SCHEDULED_REVERIFY run per (event,slot)
    no matter how many passes hit the same slot."""
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H") + f"{now.minute // 5:02d}"


def scheduled_reverify_due(db: Database, *, event_id: int,
                           claim_id: int | None = None,
                           now: datetime | None = None) -> bool:
    """True when no run exists for this (event, claim, slot) — prevents
    duplicate scheduled runs within one reverify window."""
    slot = due_reverify_slot(now)
    key = f"reverify:{event_id}:{claim_id or 0}:{slot}"
    return db.query_one(
        "SELECT 1 AS x FROM verification_runs WHERE dedupe_key=?", (key,)) is None
