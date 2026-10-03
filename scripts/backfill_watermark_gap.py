"""One-shot backfill of messages lost to the pre-fix watermark bug (ops script,
runs inside the container, touches only akhbot data)."""
import asyncio
import json

import httpx

from app.core.textnorm import detect_language
from app.db.database import Database
from app.db.repo import RawItemsRepo, SourcesRepo
from app.ingestion.telegram_web import fingerprints_for, parse_preview_page

GAPS = {
    8: ("withyashar", [24713, 24714, 24731, 24757, 24786, 24787, 24788,
                       24802, 24803, 24804, 24805, 24806, 24807, 24808,
                       24809, 24810, 24811, 24812, 24813, 24814, 24815,
                       24816, 24817]),
    10: ("naya_foriraq", [92269, 92270, 92271, 92272, 92273, 92308, 92322,
                          92323, 92328, 92390, 92391, 92392, 92393, 92394]),
}


async def backfill() -> int:
    db = Database("/data/akhbot.db")
    items = RawItemsRepo(db)
    inserted = 0
    async with httpx.AsyncClient(
            timeout=25, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; akhbot/0.1)"}) as client:
        for sid, (handle, wanted) in GAPS.items():
            src = SourcesRepo(db).get(sid)
            activated = str(src["activated_at"] or "")[:19]
            need = set(wanted)
            before = max(wanted) + 1
            for _ in range(15):
                url = f"https://t.me/s/{handle}" + (f"?before={before}" if before else "")
                r = await client.get(url)
                if r.status_code != 200:
                    break
                msgs = parse_preview_page(r.text)
                if not msgs:
                    break
                for m in msgs:
                    mid = int(m["post"].split("/")[-1])
                    if mid not in need:
                        continue
                    ek = f"tgweb:{m['post']}"
                    if items.exists(sid, ek):
                        need.discard(mid)
                        continue
                    title = m["text"].split("\n", 1)[0][:200]
                    fp = fingerprints_for(f"https://t.me/{m['post']}", title, m["text"])
                    pub = m.get("published") or ""
                    act = bool(not activated or (pub and pub[:19] >= activated))
                    items.insert(source_id=sid, platform="telegram", external_key=ek,
                                 url=f"https://t.me/{m['post']}",
                                 canonical_url=fp["canonical_url"], title=title,
                                 text=m["text"], language=detect_language(m["text"]),
                                 published_at=pub, lineage_key=f"tgweb:{handle}",
                                 activation_ok=1 if act else 0, fingerprints=fp)
                    inserted += 1
                    need.discard(mid)
                oldest = min(int(m["post"].split("/")[-1]) for m in msgs)
                before = oldest
                if not need or oldest < min(wanted) - 5:
                    break
            print(handle, "still missing:", sorted(need))
    db.close()
    return inserted


if __name__ == "__main__":
    print("backfilled:", asyncio.run(backfill()))
