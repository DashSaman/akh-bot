#!/usr/bin/env python3
"""Benchmark 9Router providers for ar/en/he -> fa translation quality.

Usage: python scripts/provider_bench.py [model ...]
Prints PASS/FAIL per (model, lang) + latency; conservative failures only.
"""
import json
import os
import re
import sys
import time

import httpx

BASE = os.environ.get("NINEROUTER_URL", "http://nine-router:20128/v1")
KEY = os.environ["NINEROUTER_KEY"]

DEFAULTS = [
    "groq/qwen/qwen3.8-27b",
    "groq/openai/gpt-oss-120b",
    "samba/DeepSeek-V3.2",
    "samba/Meta-Llama-3.3-70B-Instruct",
    "samba/MiniMax-M3",
    "samba/gpt-oss-120b",
    "openrouter/nvidia/nemotron-3.5-lightning:free",
]

TASKS = [
    ("ar", "قالت مصادر أمنية إن 3 مسيّرات أطلقت نيرانها على قاعدة عسكرية في جنوب لبنان، ولم يؤكد الجيش الإسرائيلي الحادثة حتى الآن."),
    ("en", "Officials said Boeing delivered 47 aircraft in March, but the airline denied any link to the crash."),
    ("he", "דובר צה\"ל לא אישר כי 12 חיילים נפצעו במהלך הפעילות בצפון רצועת עזה, ומקורות עבריים דיווחו על תקרית מתמשכת."),
]

BAD_SCRIPT = re.compile(r"[\u0590-\u05FF]+|[A-Za-z]{3,}|\u064A|\u0649|\u0629")


def ask(model, src_lang, text):
    prompt = (
        f"Translate this {src_lang} news sentence to Persian (Farsi). "
        "Keep all numbers and proper names exactly. Preserve negation and "
        "uncertainty wording. Reply with ONLY the Persian translation.\n\n" + text
    )
    t0 = time.time()
    try:
        r = httpx.post(
            BASE + "/chat/completions",
            headers={"Authorization": "Bearer " + KEY},
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 400, "temperature": 0.2, "stream": False},
            timeout=90,
        )
    except Exception as e:
        return {"ok": False, "err": "EXC " + str(e)[:80], "dt": time.time() - t0}
    dt = time.time() - t0
    if r.status_code != 200:
        return {"ok": False, "err": f"HTTP {r.status_code}: {r.text[:100]}", "dt": dt}
    try:
        try:
            body = r.json()
        except Exception:
            body = json.JSONDecoder().raw_decode(r.text)
        content = (body["choices"][0].get("message", {}).get("content") or "").strip()
    except Exception:
        return {"ok": False, "err": "parse:" + r.text[:60], "dt": dt}
    return {"ok": True, "text": content, "dt": dt, "served": body.get("model", "")}


_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹"
                             "٠١٢٣٤٥٦٧٨٩",
                             "0123456789" * 2)


def check(src, out):
    fails = []
    norm = out.translate(_FA_DIGITS)  # Persian/Arabic digits count as preserved
    for n in re.findall(r"\d+", src):
        if n not in norm:
            fails.append(f"num {n}")
    bad = BAD_SCRIPT.findall(out)
    if bad:
        fails.append("leak:" + ",".join(bad[:3]))
    return fails


def main():
    models = sys.argv[1:] or DEFAULTS
    results = {}
    for m in models:
        per = []
        for lang, text in TASKS:
            res = ask(m, lang, text)
            if not res["ok"]:
                per.append((lang, "ERR", res["err"], res["dt"]))
                continue
            fails = check(text, res["text"])
            per.append((lang, "FAIL" if fails else "PASS", ";".join(fails) or res["text"][:50], res["dt"]))
        ok = all(p[1] == "PASS" for p in per)
        avg = round(sum(p[3] for p in per) / max(1, len(per)), 2)
        results[m] = {"pass": ok, "avg_s": avg}
        print(f"MODEL {m} -> {'PASS' if ok else 'FAIL'} (avg {avg}s)")
        for lang, st, info, dt in per:
            print(f"  {lang}: {st} [{dt:.1f}s] {info[:90]}")
    print("SUMMARY " + json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
