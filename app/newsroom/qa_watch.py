"""Independent 24/7 post-publication QA watcher for Rasteh.

The watcher audits recently SENT foreign-source stories against authoritative
raw evidence. Clean repairs are written back to the Story and routed through
the canonical publish_edit outbox; it never calls Telegram directly.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from app.brand import load_brand
from app.config import get_settings
from app.db.database import Database
from app.db.repo import PublicationsRepo, SettingsRepo, utcnow
from app.integrations.llm.router import FreeAiRouter
from app.newsroom.story_evolution import render_v2_public_text
from app.newsroom.translator import consistency_issues, translate_event
from app.publishing.telegram_bot import is_persian_public_text

log = logging.getLogger("akh.qa_watch")
DEFAULT_WINDOW_MINUTES = 180
DEFAULT_INTERVAL_SECONDS = 60


def _foreign_evidence(db: Database, event_id: int) -> dict | None:
    rows = db.query(
        "SELECT r.id,r.title,r.text,r.language,r.published_at,"
        " COALESCE(NULLIF(s.identity,''),s.name) source_name"
        " FROM event_items ei JOIN raw_items r ON r.id=ei.raw_item_id"
        " JOIN sources s ON s.id=r.source_id"
        " WHERE ei.event_id=? AND r.language NOT LIKE 'fa%'"
        " AND r.language NOT IN ('','und')"
        " ORDER BY ei.is_duplicate ASC,r.published_at ASC,r.id ASC",
        (event_id,),
    )
    if not rows:
        return None
    lang = str(rows[0].get("language") or "").split("-", 1)[0].lower()
    title = next((str(r.get("title") or "").strip() for r in rows if r.get("title")), "")
    chunks: list[str] = []
    for row in rows:
        for value in (row.get("title"), row.get("text")):
            text = str(value or "").strip()
            if text and text not in chunks:
                chunks.append(text)
        if sum(len(x) for x in chunks) >= 3800:
            break
    names = "، ".join(dict.fromkeys(
        str(r.get("source_name") or "").strip() for r in rows if r.get("source_name")
    ))
    return {
        "language": lang,
        "title": title,
        "evidence": "\n".join(chunks)[:4000],
        "source_names": names,
    }


def _story_issues(source: str, headline: str, lead: str) -> list[str]:
    copy = ((headline or "") + " " + (lead or "")).strip()
    issues = consistency_issues(source or "", copy)
    if copy and not is_persian_public_text(copy):
        issues.append("FOREIGN_OUTPUT")

    # Post-publication semantic QA: reject an attribution not supported by the
    # raw report. This is intentionally targeted to a real production failure.
    norm_src = (source or "").lower().replace("ي", "ی").replace("ك", "ک")
    norm_copy = copy.lower().replace("ي", "ی").replace("ك", "ک")
    if "منابع نظامی" in norm_copy and not any(marker in norm_src for marker in (
        "مصادر عسکری", "مصدر عسکری", "military sources", "military source", "منابع نظامی",
    )):
        issues.append("UNSUPPORTED_ATTRIBUTION:MILITARY_SOURCES")
    return list(dict.fromkeys(issues))


def _recent_sent_stories(db: Database, window_minutes: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat(
        timespec="seconds"
    )
    return db.query(
        "SELECT DISTINCT st.* FROM stories st"
        " JOIN publications p ON p.story_id=st.id"
        " WHERE p.status='SENT' AND p.remote_id IS NOT NULL"
        " AND p.updated_at>=? AND st.status IN ('PUBLISHED','CORRECTED')"
        " ORDER BY st.updated_at DESC",
        (cutoff,),
    )


def _latest_sent(db: Database, story_id: int) -> dict | None:
    return db.query_one(
        "SELECT * FROM publications WHERE story_id=? AND platform='telegram'"
        " AND status='SENT' AND remote_id IS NOT NULL ORDER BY id DESC LIMIT 1",
        (story_id,),
    )


def _queue_edit(db: Database, settings, story_id: int, version: int, text: str,
                *, critical: bool = True) -> int:
    from app.newsroom.v2_pipeline import _enqueue_edit

    current = db.query_one("SELECT version FROM stories WHERE id=?", (story_id,))
    if not current or int(current["version"]) != version:
        return 0
    ph = hashlib.sha256(text.encode()).hexdigest()
    pub_id = PublicationsRepo(db).upsert(story_id, "telegram", ph, version)
    _enqueue_edit(db, settings, story_id, text, ph, pub_id, critical)
    return pub_id


async def qa_pass(db: Database, settings, brand, router, *,
                  window_minutes: int = DEFAULT_WINDOW_MINUTES,
                  dry_run: bool = False) -> dict[str, int]:
    stats = {"checked": 0, "flagged": 0, "repaired": 0, "held": 0, "failed": 0, "stale": 0}
    state = SettingsRepo(db)
    if not dry_run:
        state.set("qa_watch_last_run", utcnow())

    for story in _recent_sent_stories(db, window_minutes):
        evidence = _foreign_evidence(db, int(story["event_id"]))
        if not evidence or not evidence["evidence"]:
            continue
        stats["checked"] += 1
        issues = _story_issues(evidence["evidence"], story["headline"], story["lead"])
        if not issues:
            continue

        stats["flagged"] += 1
        log.warning(
            "QA_WATCH flagged story=%s event=%s issues=%s",
            story["id"], story["event_id"], issues,
        )
        if dry_run:
            continue

        repair = await translate_event(
            router,
            evidence["title"] or str(story["headline"] or ""),
            evidence["evidence"],
            db=None,  # QA never trusts an old translation cache
            source_language=evidence["language"],
        )
        repair_issues = (
            _story_issues(
                evidence["evidence"], repair.get("headline", ""), repair.get("lead", "")
            ) if repair else []
        )

        # Translation yields control for provider calls. A newer correction must
        # win over this snapshot, whether the old repair succeeds or fails.
        current = db.query_one("SELECT version,updated_at FROM stories WHERE id=?", (story["id"],))
        if (not current or current["version"] != story["version"]
                or current["updated_at"] != story["updated_at"]):
            stats["stale"] += 1
            continue

        prior = _latest_sent(db, int(story["id"]))
        if not prior:
            stats["failed"] += 1
            state.set("qa_watch_last_failure", json.dumps(
                {"story_id": story["id"], "issues": issues, "reason": "NO_SENT_TARGET"},
                ensure_ascii=False,
            ))
            continue

        try:
            draft = json.loads(story.get("draft_json") or "{}")
        except (TypeError, ValueError):
            draft = {}
        source_names = str(draft.get("source_names") or "") or evidence["source_names"]

        if not repair or repair_issues:
            changed = db.execute(
                "UPDATE events SET status='HELD',quality_hold='HOLD_TRANSLATION_QUALITY'"
                " WHERE id=? AND EXISTS (SELECT 1 FROM stories WHERE id=? AND version=? AND updated_at=?)",
                (story["event_id"], story["id"], story["version"], story["updated_at"]))
            if not changed.rowcount:
                stats["stale"] += 1
                continue
            stats["held"] += 1
            state.set("qa_watch_last_failure", json.dumps(
                {
                    "story_id": story["id"],
                    "issues": issues,
                    "repair_issues": repair_issues,
                    "reason": "REPAIR_UNAVAILABLE_OR_REJECTED",
                },
                ensure_ascii=False,
            ))
            continue

        content = {
            "headline": repair["headline"],
            "lead": repair.get("lead", ""),
            "details": [],
            "lifecycle": story.get("lifecycle") or "PROVISIONAL",
        }
        text = render_v2_public_text(content, brand, source_names)
        new_draft = dict(draft)
        new_draft.update({
            "headline": repair["headline"],
            "lead": repair.get("lead", ""),
            "details": [],
            "platform_variants": {"telegram": text},
            "generation_mode": "QA_REPAIR",
            "qa_repaired": True,
        })
        version = int(story["version"]) + 1
        now = utcnow()
        with db.tx() as conn:
            changed = conn.execute(
                "UPDATE stories SET headline=?,lead=?,draft_json=?,version=?,updated_at=?"
                " WHERE id=? AND version=? AND updated_at=?",
                (
                    repair["headline"], repair.get("lead", ""),
                    json.dumps(new_draft, ensure_ascii=False), version, now, story["id"],
                    story["version"], story["updated_at"],
                ),
            )
            if not changed.rowcount:
                stats["stale"] += 1
                continue
            conn.execute("UPDATE events SET quality_hold='',status='PUBLISHED' WHERE id=?"
                         " AND quality_hold='HOLD_TRANSLATION_QUALITY'", (story["event_id"],))
            conn.execute(
                "INSERT OR IGNORE INTO story_versions"
                "(story_id,version,snapshot_json,change_note,created_at) VALUES(?,?,?,?,?)",
                (
                    story["id"], version, json.dumps(new_draft, ensure_ascii=False),
                    "24x7 QA translation repair: " + ",".join(issues), now,
                ),
            )
        _queue_edit(db, settings, int(story["id"]), version, text, critical=True)
        state.set("qa_watch_last_repair", json.dumps(
            {"story_id": story["id"], "issues": issues, "at": now}, ensure_ascii=False
        ))
        stats["repaired"] += 1
        log.warning("QA_WATCH repair queued story=%s issues=%s", story["id"], issues)

    return stats


def _make_router(db: Database) -> FreeAiRouter:
    state = SettingsRepo(db)
    disabled = {
        n.split(":", 1)[1]
        for n in (state.get("ai_disabled") or "").split(",")
        if n and ":" in n
    }
    order = [n for n in (state.get("ai_priority") or "").split(",") if n] or None
    return FreeAiRouter(disabled=disabled, priority_order=order)


async def run(*, once: bool = False, dry_run: bool = False,
              interval: int = DEFAULT_INTERVAL_SECONDS,
              window_minutes: int = DEFAULT_WINDOW_MINUTES) -> None:
    settings = get_settings()
    db = Database(settings.db_path)
    brand = load_brand(settings.brand_config)
    router = _make_router(db)
    try:
        while True:
            try:
                stats = await qa_pass(
                    db, settings, brand, router,
                    window_minutes=window_minutes, dry_run=dry_run,
                )
                log.info("QA_WATCH pass: %s", stats)
            except Exception:  # noqa: BLE001
                log.exception("QA_WATCH pass failed; continuing")
            if once:
                return
            await asyncio.sleep(max(30, interval))
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Rasteh 24/7 post-publication QA watcher")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--window-minutes", type=int, default=DEFAULT_WINDOW_MINUTES)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run(
        once=args.once, dry_run=args.dry_run,
        interval=args.interval, window_minutes=args.window_minutes,
    ))


if __name__ == "__main__":
    main()
