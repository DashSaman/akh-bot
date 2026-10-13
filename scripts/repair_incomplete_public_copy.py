#!/usr/bin/env python3
"""Repair already-published half/CTA-corrupted Rasteh stories by EDITing same Telegram message.

Dry-run by default. --apply updates Story draft/version and enqueues publish_edit;
it never sends a new channel message. Canonical raw items/claims are untouched.
"""
from __future__ import annotations
import argparse, json, os
from pathlib import Path

from app.brand import load_brand
from app.config import Settings
from app.core.textnorm import sha256_hex
from app.db.database import Database
from app.db.repo import JobsRepo, PublicationsRepo, StoriesRepo, utcnow
from app.newsroom.story_evolution import build_v2_content, render_v2_public_text
from app.publishing.telegram_bot import brand_signature, public_body_is_substantive

CAUTION = "⚠️ این ادعا تا این لحظه به تأیید مستقل نرسیده است."


def corrected_for(db: Database, brand, story: dict) -> tuple[dict, str]:
    event = db.query_one("SELECT * FROM events WHERE id=?", (story["event_id"],))
    claims = db.query("SELECT * FROM claims WHERE event_id=? ORDER BY id", (story["event_id"],))
    if not event or not claims:
        raise RuntimeError("missing event/claims")
    draft = json.loads(story["draft_json"] or "{}")
    content = build_v2_content(event, claims, max_details=3)
    if not content:
        raise RuntimeError("cannot build complete public content")
    text = render_v2_public_text(content, brand, draft.get("source_names") or "")
    old = ((draft.get("platform_variants") or {}).get("telegram") or "")
    if CAUTION in old:
        sig = brand_signature(brand, True)
        body = text.replace(sig, "").rstrip()
        text = (body + "\n\n" + CAUTION + "\n\n" + sig).strip() if sig else body + "\n\n" + CAUTION
    if "بیشتر بخوانید" in text:
        raise RuntimeError("orphan CTA survived renderer")
    if content["headline"].rstrip().endswith(("…", "...")):
        raise RuntimeError("incomplete headline survived renderer")
    if not public_body_is_substantive(text):
        raise RuntimeError("corrected output failed final body gate")
    draft["headline"] = content["headline"]
    draft["lead"] = content.get("lead", "")
    draft["details"] = content.get("details", [])
    draft.setdefault("platform_variants", {})["telegram"] = text
    return draft, text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--story-id", action="append", type=int, required=True)
    args = ap.parse_args()

    settings = Settings()
    brand = load_brand(settings.brand_config)
    db = Database(os.path.join(settings.data_dir, "akhbot.db"))
    stories = StoriesRepo(db)
    pubs = PublicationsRepo(db)
    jobs = JobsRepo(db)
    backups = []

    try:
        for sid in args.story_id:
            story = stories.get(sid)
            if not story:
                raise SystemExit(f"story {sid}: not found")
            prior = db.query_one(
                "SELECT * FROM publications WHERE story_id=? AND platform='telegram' "
                "AND status='SENT' AND remote_id IS NOT NULL ORDER BY id DESC LIMIT 1", (sid,))
            if not prior:
                raise SystemExit(f"story {sid}: no SENT Telegram target")
            draft, text = corrected_for(db, brand, story)
            old_text = (json.loads(story["draft_json"] or "{}").get("platform_variants") or {}).get("telegram") or ""
            backups.append({
                "story_id": sid, "remote_id": prior["remote_id"], "version": story["version"],
                "headline": story["headline"], "draft_json": story["draft_json"], "old_text": old_text,
                "new_text": text,
            })
            print(json.dumps({
                "story_id": sid, "remote_id": prior["remote_id"], "apply": args.apply,
                "old_has_read_more": "بیشتر بخوانید" in old_text,
                "old_head_ellipsis": (story["headline"] or "").rstrip().endswith(("…", "...")),
                "new_headline": draft["headline"], "new_text": text,
            }, ensure_ascii=False))

        if not args.apply:
            return 0

        stamp = utcnow().replace(":", "").replace("+", "_")
        path = Path(settings.data_dir) / "backups" / f"public-copy-repair-{stamp}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(backups, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(path, 0o600)

        for item in backups:
            sid = int(item["story_id"])
            story = stories.get(sid)
            draft, text = corrected_for(db, brand, story)
            lifecycle = story.get("lifecycle") or "PROVISIONAL"
            version = stories.set_lifecycle(
                sid, lifecycle,
                "owner-fix: complete public copy; remove orphan source CTA; same-message edit",
                draft,
            )
            # set_lifecycle versions the draft but intentionally does not alter
            # headline/lead columns; keep canonical Story fields in sync so a
            # later re-render can never resurrect the old ellipsis headline.
            db.execute(
                "UPDATE stories SET headline=?, lead=?, updated_at=? WHERE id=? AND version=?",
                (draft["headline"], draft.get("lead", ""), utcnow(), sid, version),
            )
            payload_hash = sha256_hex(text)
            pub_id = pubs.upsert(sid, "telegram", payload_hash, version)
            job_id = jobs.enqueue(
                "publish_edit",
                {"story_id": sid, "platform": "telegram", "payload_hash": payload_hash,
                 "text": text, "publication_id": pub_id},
                priority=99,
                dedupe_key=f"complete-copy-repair:{sid}:{payload_hash[:16]}",
            )
            print(json.dumps({"story_id": sid, "version": version, "publication_id": pub_id,
                              "job_id": job_id, "backup": str(path)}, ensure_ascii=False))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
