"""Isolated translation qualification for FCC-discovered or 9Router candidates.

Does not open the newsroom DB, call Telegram, enqueue jobs, or touch production
state. Default is OFFLINE inventory; --live is explicitly opt-in, restricted
to already owner-approved zero-cost routes supplied via the existing gateway.
No API keys, headlines, or secret payloads are written to the repository.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import re

ALLOWED_FREE_MODELS = (
    "groq/openai/gpt-oss-120b",
    "groq/qwen/qwen3.8-27b",
    "cf/@cf/mistralai/mistral-small-3.1-24b-instruct",
    "zai/glm-4.5-flash",
)

# Controlled fictional tests: no production/current public news.
FIXTURES = {
    "en": (
        "On Tuesday in New York, Abbas Araghchi denied that Iran had "
        "approved a deal affecting 3,200 workers; the claim remains unconfirmed."
    ),
    "ar": (
        "قال عباس عراقجي في نيويورك يوم الثلاثاء إن إيران لم توافق على اتفاق "
        "يتعلق بـ 3200 عامل، ولا يزال التقرير غير مؤكد."
    ),
    "he": (
        "ביום שלישי בניו יורק דווח כי עבאס עראקצ'י הכחיש שאיראן אישרה "
        "הסכם הנוגע ל-3200 עובדים. הדיווח לא אומת."
    ),
}


def evaluate(source: str, headline: str, lead: str) -> list[str]:
    from app.newsroom.translator import consistency_issues
    from app.verification.gates import numbers_in
    from app.publishing.telegram_bot import is_persian_public_text

    output = (headline + " " + lead).strip()
    failures = consistency_issues(source, output)
    if not is_persian_public_text(output):
        failures.append("NON_PERSIAN")
    if not numbers_in(source).issubset(numbers_in(output)):
        failures.append("DROPPED_NUMBER")
    if not any(x in output for x in ("عراقچی", "عراقجي", "عراقچی", "عراقچي")):
        failures.append("DROPPED_NAME")
    if "نیویورک" not in output and "نیویورك" not in output:
        failures.append("DROPPED_PLACE")
    if not any(x in output for x in ("تأیید نشده", "تایید نشده", "تأییدنشده", "تاییدنشده", "راستی‌آزمایی نشده", "تأیید", "تایید", "نامشخص")):
        failures.append("LOST_UNCERTAINTY")
    if not any(x in output for x in ("نکرد", "نشده", "نیست", "نپذیرفت", "موافقت نکرد")):
        failures.append("LOST_NEGATION")
    return sorted(set(failures))


async def run_live(model: str, langs: tuple[str, ...]) -> list[dict]:
    from app.integrations.llm.router import FreeAiRouter
    from app.integrations.llm.base import extract_json
    from app.newsroom.translator import TRANSLATE_SYSTEM
    from app.integrations.llm.base import wrap_untrusted

    if model not in ALLOWED_FREE_MODELS:
        raise ValueError("Model not in validated zero-cost candidate allowlist")
    key = os.environ.get("OPENAI_COMPAT_API_KEY", "")
    base = os.environ.get("OPENAI_COMPAT_BASE_URL", "")
    if not key or not base:
        raise ValueError("Gateway not configured (credentials are never displayed)")
    env = {
        "ZERO_COST_MODE": "true", "AI_FREE_ONLY": "true",
        "AI_PROVIDER_PRIORITY": "openai_compat",
        "OPENAI_COMPAT_BASE_URL": base, "OPENAI_COMPAT_API_KEY": key,
        "OPENAI_COMPAT_MODEL": model,
        "OPENAI_COMPAT_FALLBACK_MODELS": "",
    }
    router = FreeAiRouter(env=env)
    results = []
    for lang in langs:
        start = time.monotonic()
        try:
            # Direct *one model* invocation, no invisible fallback substitution.
            raw = await router._call(
                router.states[0], TRANSLATE_SYSTEM,
                wrap_untrusted(FIXTURES[lang]), max_tokens=900
            )
            obj = extract_json(raw)
            errors = evaluate(FIXTURES[lang], str(obj.get("headline") or ""),
                              str(obj.get("lead") or ""))
            results.append({"language": lang, "passed": not errors,
                            "error_codes": errors,
                            "latency_ms": int((time.monotonic()-start)*1000)})
        except Exception as exc:
            # No provider response bodies, tokens or keys in results.
            # Expose the HTTP class for troubleshooting, never raw error bodies
            # (which may contain sensitive upstream payloads).
            status = re.search(r"HTTP\s+(\d{3})", str(exc))
            safe_code = f"HTTP_{status.group(1)}" if status else type(exc).__name__
            results.append({"language": lang, "passed": False,
                            "error_codes": [safe_code],
                            "latency_ms": int((time.monotonic()-start)*1000)})
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="Opt in to no-DB API calls")
    ap.add_argument("--model", choices=ALLOWED_FREE_MODELS)
    ap.add_argument("--langs", nargs="*", choices=FIXTURES, default=list(FIXTURES))
    args = ap.parse_args()
    if not args.live:
        print(json.dumps({"mode": "offline", "network_calls": 0,
                          "allowed_models": ALLOWED_FREE_MODELS,
                          "fixtures": list(FIXTURES)}, ensure_ascii=False))
        return
    if not args.model:
        ap.error("--live requires --model")
    print(json.dumps({"mode": "live isolated no-db no-publisher",
                      "model": args.model,
                      "results": asyncio.run(run_live(args.model, tuple(args.langs)))},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
