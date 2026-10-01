"""Legacy draft normalization (Part 1 T2) — idempotent, never invents facts."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import Database  # noqa: E402

_ICON = re.compile(r"^[\U0001F7E2\U0001F534\U0001F7E0\u26A0\u274C]\s*")
_EMOJI = re.compile(r"^[\U0001F000-\U0001FAFF]+\s*")


def split_rendered(text: str):
    lines = (text or "").split("\n")
    headline = _EMOJI.sub("", _ICON.sub("", lines[0] if lines else "")).replace("**", "").strip()
    body = []
    for ln in lines[1:]:
        t = ln.strip()
        if t.startswith(("\u0645\u0646\u0628\u0639:", "\u0645\u0646\u0627\u0628\u0639:", "\u2014", "\U0001F194")):
            break
        if t:
            body.append(t)
    return headline[:140], " ".join(body).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--db", default=os.environ.get("AKHBOT_DB", "/data/akhbot.db"))
    args = ap.parse_args()

    db = Database(args.db)
    already = converted = unsafe = 0
    for r in db.query("SELECT id, draft_json FROM stories ORDER BY id"):
        try:
            draft = json.loads(r["draft_json"])
        except Exception:
            unsafe += 1
            continue
        if draft.get("legacy_blob"):
            already += 1
            continue
        h = (draft.get("headline") or "").replace("**", "").strip()
        lead = (draft.get("lead") or "").strip()
        rendered = draft.get("platform_variants", {}).get("telegram", "")
        if not rendered or not draft.get("headline"):
            unsafe += 1
            continue
        raw_h = (draft.get("headline") or "")
        if h and lead and h != lead and "**" not in raw_h and not raw_h.startswith(
                ("🟢", "🔴", "🟠")):
            already += 1
            continue
        rh, rlead = split_rendered(rendered)
        if not rh:
            unsafe += 1
            continue
        rlead = "" if rlead == rh else rlead  # compact story: headline-only, never invent
        converted += 1
        if args.apply:
            draft.update(headline=rh, lead=rlead, details=draft.get("details", []),
                         legacy_blob=True)
            draft.setdefault("language", "fa")
            db.execute("UPDATE stories SET headline=?, lead=?, draft_json=? WHERE id=?",
                       (rh, rlead, json.dumps(draft, ensure_ascii=False), r["id"]))
    print(f"{'APPLIED' if args.apply else 'DRY-RUN'}: scanned={already+converted+unsafe} "
          f"converted={converted} already={already} unsafe={unsafe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
