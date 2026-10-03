"""Private live check: FreeAiRouter vs Groq (no secrets printed, nothing published)."""
import asyncio
import json

from app.integrations.llm.router import FreeAiRouter

SAMPLES = {
    "en": 'Translate to Persian. Keep numbers EXACT, keep negation, do not escalate certainty. Return JSON {"fa": "..."}\nText: "The minister said 47 people were injured and 3 died."',
    "ar": 'Translate to Persian. Keep numbers EXACT, keep negation, do not escalate certainty. Return JSON {"fa": "..."}\nText: "قال الجيش إن الهجوم لم يستهدف أي مدنيين وأن 12 شخصا اعتقلوا."',
    "he": 'Translate to Persian. Keep numbers EXACT, keep negation, do not escalate certainty. Return JSON {"fa": "..."}\nText: "הרמטכ\"ל אמר כי 9 טילים יורטו ולא היו נפגעים."',
}


async def main() -> None:
    router = FreeAiRouter()
    print("providers_before:", json.dumps(router.provider_states(), ensure_ascii=False))
    print("available:", router.available)
    for lang, user in SAMPLES.items():
        out = await router.chat_json(
            system="You are a translation engine. Reply with JSON only.",
            user=user, max_tokens=300)
        print(f"result[{lang}]:", json.dumps(out, ensure_ascii=False))
    print("providers_after:", json.dumps(router.provider_states(), ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
