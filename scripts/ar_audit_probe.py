"""Diagnose: call provider once, run the SAME audit translate_event runs,
print exactly what the audit saw (no rejection hiding). Paced to avoid 429."""
import asyncio
import sys

from app.integrations.llm.base import wrap_untrusted
from app.integrations.llm.router import FreeAiRouter
from app.newsroom.translator import (TRANSLATE_SYSTEM, _NEG_AR, _NEG_FA,
                                     _has_any, consistency_issues)

CASES = [
    ("ar", "قصف إسرائيلي على ضاحية بيروت",
     "قال مصدر عسكري إن الغارة لم تستهدف مدنيين وأن 12 شخصا اعتقلوا وأفرج عن 3"),
    ("he", "עימות בגבול הצפוני",
     "דובר צה\"ל אמר כי 9 טילים יורטו ולא היו נפגעים, לדבריו."),
]


async def main() -> None:
    router = FreeAiRouter()
    for lang, title, evidence in CASES:
        await asyncio.sleep(15)
        out = await router.chat_json(
            system=TRANSLATE_SYSTEM,
            user=wrap_untrusted(title + "\n\n" + evidence[:4000]),
            max_tokens=1200)
        if not out:
            print(f"[{lang}] provider None (429/degraded)")
            continue
        gen = (out.get("headline") or "") + " " + (out.get("lead") or "")
        issues = consistency_issues(evidence, gen)
        hit = [t for t in _NEG_FA if t in gen]
        print(f"[{lang}] gen={gen}")
        print(f"[{lang}] neg_tokens_hit={hit} src_neg={_has_any(evidence, _NEG_AR)} issues={issues}")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
