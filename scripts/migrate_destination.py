"""Migrate misdirected private-chat deliveries to the real channel (run in container)."""
import asyncio
import json
import os
import sys

sys.path.insert(0, "/srv")
os.environ.setdefault("DATA_DIR", "/data")

from app.brand import load_brand
from app.config import Settings
from app.core.textnorm import sha256_hex
from app.db.database import Database
from app.db.repo import JobsRepo, PublicationsRepo, StoriesRepo
from app.publishing.telegram_bot import build_public_text, TelegramBotPublisher

s = Settings()
db = Database("/data/akhbot.db")
brand = load_brand("config/brand.yml")
PRIVATE = "5504556066"


async def main():
    pub = TelegramBotPublisher(s.telegram_bot_token, s.telegram_publish_target)
    v = await pub.validate_publish_target()
    tail = str(v.get("chat_id"))[-6:] if v.get("valid") else "?"
    print("PUBLISH TARGET valid:", v["valid"], "| type=channel | id …", tail,
          "| title:", v.get("title"), "| @", v.get("username"))
    assert v["valid"], v
    # legacy rows (pre-column) went to the private chat — mark historical
    db.execute("UPDATE publications SET chat_id=? WHERE chat_id IS NULL", (PRIVATE,))
    for st in db.query("SELECT * FROM stories ORDER BY id"):
        target = "PROVISIONAL" if st["id"] == 2 else ("CONFIRMED_OFFICIAL" if st["id"] != 2 else "CONFIRMED")
        draft = json.loads(st["draft_json"])
        text = build_public_text(target, draft["platform_variants"]["telegram"], brand, "hidden", True)
        ph = sha256_hex(text)
        prior = db.query_one(
            "SELECT * FROM publications WHERE story_id=? AND platform='telegram' "
            "AND status='SENT' ORDER BY id DESC LIMIT 1", (st["id"],))
        if prior and prior["chat_id"] == str(s.telegram_publish_target):
            print("story", st["id"], "already delivered to channel — skip")
            continue
        draft = dict(draft, platform_variants={"telegram": text})
        StoriesRepo(db).set_lifecycle(st["id"], target.replace("_OFFICIAL", ""),
                                      "migrate-to-channel", draft)
        pid = PublicationsRepo(db).upsert(st["id"], "telegram", ph, 2)
        jid = JobsRepo(db).enqueue(
            "publish_telegram",
            {"story_id": st["id"], "platform": "telegram", "payload_hash": ph,
             "text": text, "publication_id": pid},
            dedupe_key="pub:tg:{}:{}".format(st["id"], ph[:16]))
        print("migrated story", st["id"], "→ pub", pid, "job", jid)


asyncio.run(main())
