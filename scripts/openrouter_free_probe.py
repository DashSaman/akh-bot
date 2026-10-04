#!/usr/bin/env python3
"""Probe OpenRouter free models for Persian translation quality."""
import os
import re
import time

import httpx

KEY = os.environ["OPENROUTER_API_KEY"]
AR = "قالت مصادر أمنية إن 3 مسيّرات أطلقت نيرانها على قاعدة عسكرية في جنوب لبنان، ولم يؤكد الجيش الإسرائيلي الحادثة حتى الآن."
EN = "Officials said Boeing delivered 47 aircraft in March, but the airline denied any link to the crash."
BAD = re.compile(r"[\u0590-\u05FF]+|[A-Za-z]{3,}|\u064A|\u0649|\u0629")
CANDIDATES = [
    "qwen/qwen3.8-27b:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "thinkingmachines/inkling:free",
]


def extract(j):
    msg = j["choices"][0]["message"]
    c = (msg.get("content") or "").strip()
    if not c:
        c = (msg.get("reasoning") or "").strip()
    return c


def run(model, text, lang):
    t0 = time.time()
    r = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": "Bearer " + KEY},
        json={"model": model,
              "messages": [{"role": "user", "content":
                            f"Translate this {lang} news sentence to Persian (Farsi). "
                            "Keep all numbers and proper names exactly. Preserve negation and uncertainty. "
                            "Reply with ONLY the Persian translation.\n\n" + text}],
              "max_tokens": 400, "temperature": 0.2},
        timeout=120,
    )
    dt = time.time() - t0
    if r.status_code != 200:
        return f"HTTP {r.status_code} {r.text[:60]}", dt, False, []
    txt = extract(r.json())
    nums = all(n in txt for n in re.findall(r"\d+", text))
    bad = BAD.findall(txt)
    return txt, dt, nums, bad


for m in CANDIDATES:
    try:
        ar, dt1, n1, b1 = run(m, AR, "Arabic")
        if isinstance(ar, str) and ar.startswith("HTTP"):
            print(f"{m} -> {ar} [{dt1:.1f}s]")
            continue
        ok = n1 and not b1
        print(f"{m} -> {'PASS' if ok else 'FAIL'} ar[{dt1:.1f}s] nums={n1} leak={b1[:2]} sample={ar[:36]}")
    except Exception as e:
        print(f"{m} -> EXC {str(e)[:70]}")
