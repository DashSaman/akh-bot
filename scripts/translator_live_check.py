"""Live end-to-end translator check against real Groq on a TEMP DB.

Exercises the exact production path: translate_event (TRANSLATE_SYSTEM prompt,
consistency audit, Persian gate) + llm_cache write/read. Nothing published,
no prod tables touched.
"""
import asyncio
import json
import re
import sys
import tempfile

from app.integrations.llm.base import wrap_untrusted
from app.integrations.llm.router import FreeAiRouter
from app.newsroom.translator import TRANSLATE_SYSTEM, translate_event

CASES = [
    ("ar", "قصف إسرائيلي على ضاحية بيروت",
     "قال مصدر عسكري إن الغارة لم تستهدف مدنيين وأن 12 شخصا اعتقلوا وأفرج عن 3"),
    ("en", "Ceasefire talks stall in Doha",
     "Officials said 47 people were injured and 3 died; the deal may collapse, reports say."),
    ("he", "עימות בגבול הצפוני",
     "דובר צה\"ל אמר כי 9 טילים יורטו ולא היו נפגעים, לדבריו."),
]


async def main() -> int:
    tmp = tempfile.mktemp(suffix=".db")
    from app.db.database import Database
    db = Database(tmp)
    from app.db.migrate import apply_migrations
    apply_migrations(db)

    router = FreeAiRouter()
    failures = 0
    raw_ar = None
    for lang, title, evidence in CASES:
        # first: raw provider output (diagnosis only, bypasses audit)
        if lang == "ar":
            raw_ar = await router.chat_json(
                system=TRANSLATE_SYSTEM,
                user=wrap_untrusted(title + "\n\n" + evidence[:4000]),
                max_tokens=1200)
            print(f"[{lang}] RAW provider output: {json.dumps(raw_ar, ensure_ascii=False)}")
        out = await translate_event(router, title, evidence,
                                    db=db, source_language=lang)
        if out is None:
            print(f"[{lang}] FAIL (rejected or provider error)")
            failures += 1
            continue
        print(f"[{lang}] cache={out.get('cache')} headline={out['headline']}")
        print(f"[{lang}] lead={out['lead']}")
        # numbers must survive: all source digits appear in Persian output
        import re
        fa_digits = "۰۱۲۳۴۵۶۷۸۹"
        def fa_num(s):
            return s
        out_text = out["headline"] + " " + out["lead"]
        # map Persian digits back to ASCII for comparison
        for i, d in enumerate(fa_digits):
            out_text = out_text.replace(d, str(i))
        src_nums = set(re.findall(r"\d+", title + " " + evidence))
        missing = [n for n in src_nums if n not in out_text]
        if missing:
            print(f"[{lang}] NUMBER-MISMATCH missing={missing}")
            failures += 1
    # cache hit check: second identical call of a SUCCESSFUL case must be HIT
    out2 = await translate_event(router, CASES[1][1], CASES[1][2],
                                 db=db, source_language="en")
    print("cache-hit:", (out2 or {}).get("cache"))
    if (out2 or {}).get("cache") != "HIT":
        failures += 1
    print("FAILURES:", failures)
    db.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
