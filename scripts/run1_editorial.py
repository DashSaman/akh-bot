"""Editorial publish run #1 (agent-as-writer while GLM key is pending).

Publishes through the REAL ledger/jobs path to the production channel.
Facts are strictly limited to the collected raw items cited below.
"""
import os
import sys

sys.path.insert(0, "/srv")
os.environ.setdefault("DATA_DIR", "/data")

from app.core.textnorm import sha256_hex  # noqa: E402
from app.db.database import Database  # noqa: E402
from app.db.repo import (  # noqa: E402
    ClaimsRepo, EventsRepo, PublicationsRepo, JobsRepo, StoriesRepo, utcnow,
)

db = Database("/data/akhbot.db")

POSTS = [
    {
        "event_id": 3, "raw_item_id": 239,
        "state": "CONFIRMED",  # official statement: proven that it was made
        "note": "PRIMARY STATEMENT — روس‌اتم official statement via IRNA",
        "headline": "روس‌اتم: آماده‌ایم تخصص هسته‌ای صلح‌آمیز را با شرکای جهانی به اشتراک بگذاریم",
        "claims": ["مدیرعامل شرکت هسته‌ای روس‌اتم گفت روسیه آماده است تخصص خود در استفاده صلح‌آمیز از انرژی هسته‌ای با شرکای جهانی به اشتراک بگذارد"],
        "text": (
            "✅ تأیید شد | اعلام رسمی\n\n"
            "مدیرعامل شرکت دولتی هسته‌ای روس‌اتم اعلام کرد این شرکت آماده است تخصص خود در "
            "استفاده صلح‌آمیز از انرژی هسته‌ای را با شرکای جهانی به اشتراک بگذارد.\n\n"
            "این یک «اظهار رسمی» است: درستیِ خودِ اعلام از سوی منبع رسمی تأیید شده، اما "
            "سیاست‌های هسته‌ای روسیه در این زمینه به‌صورت مستقل راستی‌آزمایی نشده است.\n\n"
            "📖 منبع: ایرنا — https://www.isna.ir\n"
            "— راسته؟ | خبر و راستی‌آزمایی"
        ),
    },
    {
        "event_id": 6, "raw_item_id": 244,
        "state": "UNVERIFIED",  # watch-source only → developing label
        "note": "DEVELOPING — single Telegram watch source (withyashar citing @WarRoom)",
        "headline": "گزارش: تماس تلفنی نتانیاهو و ترامپ در ساعات آینده",
        "claims": ["به گزارش کانال تلگرامی withyashar به نقل از WarRoom، نتانیاهو طی چند ساعت آینده با ترامپ تلفنی صحبت خواهد کرد"],
        "text": (
            "🔴 خبر در حال بررسی\n\n"
            "گزارش: تماس تلفنی نتانیاهو و ترامپ در ساعات آینده\n\n"
            "به گزارش یک کانال تلگرامی خبری (withyashar به نقل از WarRoom)، بنیامین نتانیاهو "
            "ظرف چند ساعت آینده گفت‌وگوی تلفنی با دونالد ترامپ خواهد داشت.\n\n"
            "⚠️ این گزارش هنوز به‌طور مستقل تأیید نشده است و صرفاً نقل یک منبع تلگرامی است. "
            "در صورت تأیید یا رد رسمی، همین پست اصلاح و به‌روزرسانی می‌شود.\n\n"
            "📖 منبع: t.me/withyashar\n"
            "— راسته؟ | خبر و راستی‌آزمایی"
        ),
    },
    {
        "event_id": 2, "raw_item_id": 238,
        "state": "CONFIRMED",  # official call/announcement relayed by IRNA
        "note": "OFFICIAL ANNOUNCEMENT — بیمه مرکزی فراخوان via IRNA",
        "headline": "فراخوان اینشورتک‌ها برای پاسخ به ۱۰ نیاز صنعت بیمه",
        "claims": ["بیمه مرکزی به همراه معاونت علمی رئیس‌جمهوری و صندوق نوآوری فراخوانی برای پاسخ اینشورتک‌ها به ده نیاز صنعت بیمه منتشر کرده است"],
        "text": (
            "📢 اعلام رسمی\n\n"
            "فراخوان اینشورتک‌ها برای پاسخ به ۱۰ نیاز صنعت بیمه\n\n"
            "بیمه مرکزی همراه با معاونت علمی، فناوری و اقتصاد دانش‌بنیان ریاست‌جمهوری و "
            "صندوق نوآوری و شکوفایی، از شرکت‌های فناوری مالی (اینشورتک) دعوت کرده است "
            "پاسخ‌گوی ده نیاز تعریف‌شدهٔ صنعت بیمه باشند.\n\n"
            "هدف اعلام‌شده: بهره‌گیری از فناوری‌های نوین در صنعت بیمه کشور.\n\n"
            "📖 منبع: ایرنا — https://www.irna.ir\n"
            "— راسته؟ | خبر و راستی‌آزمایی"
        ),
    },
]

for p in POSTS:
    ev = EventsRepo(db).get(p["event_id"])
    if not ev:
        print("missing event", p["event_id"])
        continue
    if StoriesRepo(db).by_event(p["event_id"]):
        print("story exists for event", p["event_id"], "— skip")
        continue
    for c in p["claims"]:
        ClaimsRepo(db).upsert(p["event_id"], c, p["state"], "normal",
                              [{"item_id": p["raw_item_id"], "source_id":
                                db.query_one("SELECT source_id sid FROM raw_items WHERE id=?",
                                             (p["raw_item_id"],))["sid"],
                                "quote": c[:200]}], [], 1)
    draft = {"headline": p["headline"], "lead": p["note"], "body": [{"text": p["text"], "claim_refs": []}],
             "platform_variants": {"telegram": p["text"]}, "editorial_note": p["note"],
             "written_by": "editorial-agent-run1"}
    story_id = StoriesRepo(db).create(p["event_id"], p["headline"], p["note"], draft)
    payload_hash = sha256_hex(p["text"])
    pub_id = PublicationsRepo(db).upsert(story_id, "telegram", payload_hash, 1)
    job = JobsRepo(db).enqueue("publish_telegram",
                               {"story_id": story_id, "platform": "telegram",
                                "payload_hash": payload_hash, "text": p["text"],
                                "publication_id": pub_id},
                               dedupe_key=f"pub:tg:{story_id}:{payload_hash[:16]}")
    print(f"event={p['event_id']} story={story_id} pub={pub_id} job={job} state={p['state']} :: {p['headline'][:60]}")
print("queued at", utcnow())
