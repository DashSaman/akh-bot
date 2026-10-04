"""Direct-Groq fallback must satisfy Groq's json_object prompt rule.

Groq answers HTTP 400 when response_format=json_object is set but the word
"json" appears nowhere in the messages; the fallback adapter must therefore
inject it for any prompt, and never duplicate it when already present.
"""
import json

import httpx
import pytest

from app.integrations.llm.router import FreeAiRouter

ENV = {
    "GROQ_API_KEY": "gsk_test",
    "GROQ_MODEL": "qwen/qwen3.8-27b",
    "OPENAI_COMPAT_API_KEY": "",
    "OPENAI_COMPAT_BASE_URL": "",
}


def _router(captured):
    def handler(request):
        captured.append(json.loads(request.read()))
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"ok": true}'}}],
        })
    return FreeAiRouter(env=ENV, transport=httpx.MockTransport(handler),
                        priority_order=["groq"])


@pytest.mark.asyncio
async def test_groq_injects_json_word_when_missing():
    captured = []
    router = _router(captured)
    out = await router.chat_json(system="You are a test echo.",
                                 user="Reply with the single word: OK")
    assert out == {"ok": True}
    payload = captured[0]
    assert payload["response_format"] == {"type": "json_object"}
    texts = " ".join(m["content"] for m in payload["messages"])
    assert "json" in texts.lower(), "groq fallback must mention json"


@pytest.mark.asyncio
async def test_groq_does_not_duplicate_json_word():
    captured = []
    router = _router(captured)
    system = "You translate news. Output strict JSON only."
    await router.chat_json(system=system, user="Translate: hello")
    payload = captured[0]
    assert payload["messages"][0]["content"] == system
    assert payload["messages"][0]["content"].lower().count("json") == 1
