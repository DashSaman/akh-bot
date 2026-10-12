"""One-time, idempotent Rasteh Telegram backfill. Never send or delete posts.

Default DRY RUN. Only the latest SENT revision of an owned @RastehNews
message containing the exact preview-brand marker is eligible.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sqlite3
from pathlib import Path

from app.brand import load_brand
from app.publishing.telegram_bot import (
    TelegramBotPublisher, brand_signature, public_body_is_substantive,
    squash_duplicate_lead, to_telegram_html,
)

BAD = ("پیش‌نمایش سکوی خبری", "نام نهایی هنوز انتخاب نشده است")
PROMO = ("با ما اخبار جنگی بروز باشید", "چنل های بی سواد")
EXPECTED_CHAT = "-1004459746525"
BACKUP = Path("/data/backups/rasteh_footer_20261009_originals.json")


def cleaned_variant(original: str, signature: str) -> str:
    lines = []
    for ln in original.splitlines():
        stripped = ln.strip()
        if any(s in stripped for s in BAD):
            continue
        if any(s in stripped for s in PROMO):
            continue
        if stripped.startswith("🆔 @RastehNews"):
            continue
        # De-duplicate an already-correct signature before re-appending it.
        if stripped.startswith("— راسته؟ | خبر و راستی‌آزمایی"):
            continue
        lines.append(ln.rstrip())
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    body = squash_duplicate_lead(body)
    return body + "\n\n" + signature


def candidates(db, chat: str, signature: str, duplicate_only: bool = False):
    sql = """
        WITH latest AS (
            SELECT p.*, ROW_NUMBER() OVER (
                PARTITION BY p.chat_id, p.remote_id ORDER BY p.id DESC
            ) AS rank
            FROM publications p
            WHERE p.status='SENT' AND p.platform='telegram'
                AND p.chat_id=? AND p.remote_id IS NOT NULL
        )
        SELECT l.id AS publication_id, l.remote_id, s.id AS story_id,
               s.draft_json
        FROM latest l JOIN stories s ON s.id=l.story_id
        WHERE l.rank=1 ORDER BY CAST(l.remote_id AS INTEGER)
    """
    result = []
    for row in db.execute(sql, (chat,)).fetchall():
        try:
            draft = json.loads(row["draft_json"] or "{}")
            original = (draft.get("platform_variants") or {}).get("telegram", "")
        except (ValueError, TypeError):
            continue
        if duplicate_only:
            revised = squash_duplicate_lead(original)
        else:
            if not any(s in original for s in BAD):
                continue
            revised = cleaned_variant(original, signature)
        if revised != original:
            result.append((row, draft, original, revised))
    return result


async def repair(apply: bool, limit: int, delay: float, duplicate_only: bool = False):
    brand = load_brand(os.environ.get("BRAND_CONFIG", "config/brand.yml"))
    if not brand.decided or brand.name_fa != "راسته؟" or brand.telegram_handle != "RastehNews":
        raise RuntimeError("Abort: verified @RastehNews brand config required")
    chat = os.environ.get("TELEGRAM_PUBLISH_CHAT_ID")
    if chat != EXPECTED_CHAT:
        raise RuntimeError("Abort: production destination differs from known channel")
    signature = brand_signature(brand)
    db = sqlite3.connect("/data/akhbot.db", timeout=20)
    db.row_factory = sqlite3.Row
    all_rows = candidates(db, chat, signature, duplicate_only=duplicate_only)
    print("ELIGIBLE_UNIQUE_MESSAGES", len(all_rows), flush=True)
    for row, _, original, revised in all_rows[:3]:
        print("PREVIEW", row["remote_id"], "before_chars", len(original),
              "after_chars", len(revised), "duplicate_fixed",
              original.count("**") != revised.count("**"), flush=True)
        print("TAIL", repr(revised[-105:]), flush=True)
    if not apply:
        return
    bot = TelegramBotPublisher(os.environ["TELEGRAM_BOT_TOKEN"], chat)
    target = await bot.validate_publish_target()
    if not target.get("valid") or target.get("username", "").lower() != "rastehnews":
        raise RuntimeError("Abort: destination is not the expected @RastehNews channel")

    backup_path = (Path("/data/backups/rasteh_duplicate_20261009_originals.json")
                   if duplicate_only else BACKUP)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    original_snapshot = {str(r["story_id"]): {"message_id": r["remote_id"],
                         "publication_id": r["publication_id"], "old": old}
                         for r, _, old, _ in all_rows}
    # Never overwrite a previous original-content snapshot.
    if not backup_path.exists():
        with backup_path.open("x", encoding="utf-8") as fp:
            json.dump(original_snapshot, fp, ensure_ascii=False, indent=2)
    processed = successes = 0
    for row, draft, old, revised in all_rows:
        if limit and processed >= limit:
            break
        processed += 1
        msgid = row["remote_id"]
        if not public_body_is_substantive(revised) or len(to_telegram_html(revised)) > 4096:
            print("SKIP_INVALID", msgid, flush=True)
            continue
        response = {"ok": False}
        error = ""
        for attempt in range(5):
            response = await bot.edit_message(msgid, revised)
            if response.get("ok"):
                break
            error = str(response.get("error") or "")
            if "message is not modified" in error.lower():
                response = {"ok": True}
                break
            if "too many requests" not in error.lower():
                break
            match = re.search(r"retry after (\d+)", error, re.I)
            wait = int(match.group(1)) + 3 if match else 40
            print("RATE_LIMIT", msgid, "wait_seconds", wait, flush=True)
            await asyncio.sleep(wait)
        if not response.get("ok"):
            print("ERROR", msgid, error[:160], flush=True)
            await asyncio.sleep(delay)
            continue
        draft["platform_variants"]["telegram"] = revised
        try:
            db.execute("UPDATE stories SET draft_json=? WHERE id=? AND draft_json=?",
                       (json.dumps(draft, ensure_ascii=False), row["story_id"], row["draft_json"]))
            db.commit()
        except sqlite3.Error as exc:
            db.rollback()
            print("DB_SYNC_ERROR", msgid, str(exc)[:120], flush=True)
        successes += 1
        print("EDITED", msgid, "done", successes, "/", len(all_rows), flush=True)
        await asyncio.sleep(delay)
    print("RESULT", "processed", processed, "edited", successes,
          "eligible", len(all_rows), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=1.2)
    parser.add_argument("--duplicates", action="store_true")
    args = parser.parse_args()
    asyncio.run(repair(args.apply, args.limit, args.delay, args.duplicates))
