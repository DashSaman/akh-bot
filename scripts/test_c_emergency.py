import asyncio

from app.integrations.llm.router import FreeAiRouter


async def main():
    r = FreeAiRouter()
    out = await r.chat_json(
        system="You are a test echo.",
        user="Reply with the single word: OK",
    )
    print("ROUTER_RESULT:", str(out)[:60])


asyncio.run(main())
