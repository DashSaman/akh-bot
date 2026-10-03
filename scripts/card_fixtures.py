"""Render 10 Persian card fixtures (real DB headlines + edge cases) for visual
inspection. Output: /tmp/cards/*.png + JSON manifest."""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.environ.get("CARDS_ROOT", "/srv"))
from app.publishing.cards import render_card_v2  # noqa: E402

FIXTURES_EXTRA = [
    # edge cases beyond DB headlines
    ("**تأییدنشده**: حمله با پهپاد به کرانه غربی؛ ۱۲ زخمی و ۳ بازداشت",
     "PROVISIONAL"),
    ("بیانیه مشترک سه کشور اروپایی درباره برنامه هسته‌ای: مذاکرات در دوحه",
     "VERIFIED"),
    ("گزارش‌های متعارض درباره وضعیت فرودگاه بین‌المللی صنعا پس از انفجار",
     "CONFLICTING"),
    ("رئیس‌جمهور در نشست شورای امنیت ملی: پاسخ به تجاوز خواهد بود حساب‌شده و برون‌مرزی و متناسب با تهدید",
     "PROVISIONAL"),
]

db = sqlite3.connect("/data/akhbot.db")
db.row_factory = sqlite3.Row
rows = db.execute(
    "SELECT headline, lifecycle FROM stories WHERE lifecycle IS NOT NULL "
    "ORDER BY id DESC LIMIT 6").fetchall()

cases = [(r["headline"], r["lifecycle"] or "PROVISIONAL") for r in rows]
cases += FIXTURES_EXTRA
cases = cases[:10]

os.makedirs("/tmp/cards", exist_ok=True)
manifest = []
for i, (headline, lifecycle) in enumerate(cases):
    path = f"/tmp/cards/fixture-{i:02d}.png"
    try:
        p = render_card_v2(headline, lifecycle=lifecycle, out_path=path)
        manifest.append({"i": i, "ok": True, "lifecycle": lifecycle,
                         "headline": headline[:80], "path": p,
                         "bytes": os.path.getsize(p)})
    except Exception as ex:  # noqa: BLE001
        manifest.append({"i": i, "ok": False, "error": str(ex)[:120],
                         "headline": headline[:80]})
print(json.dumps(manifest, ensure_ascii=False, indent=1))
ok = sum(1 for m in manifest if m["ok"])
print(f"RENDERED {ok}/{len(manifest)}")
