"""LLM provider abstraction. Business logic never hard-codes GLM.

Everything collected from Telegram/X/web/RSS is UNTRUSTED DATA: it is passed to the
model strictly inside delimited data blocks, with a system instruction that content
inside those blocks is data — never instructions.
"""
from __future__ import annotations

import json
from typing import Any, Protocol

from app.core.textnorm import sha256_hex

PROMPT_VERSION = "v1"

UNTRUSTED_OPEN = "<<<UNTRUSTED-SOURCE-DATA"
UNTRUSTED_CLOSE = "END-UNTRUSTED-SOURCE-DATA>>>"


def wrap_untrusted(text: str) -> str:
    """Delimit external content; strip control characters that could hide injections."""
    cleaned = "".join(ch for ch in (text or "") if ch >= " " or ch in "\n\t")
    return f"{UNTRUSTED_OPEN}\n{cleaned[:20000]}\n{UNTRUSTED_CLOSE}"


class LlmError(Exception):
    pass


class LlmTimeout(LlmError):
    pass


class LlmMalformedJson(LlmError):
    pass


class LLMProvider(Protocol):
    name: str
    model: str

    async def chat_json(self, *, system: str, user: str, max_tokens: int = 4000,
                        temperature: float = 0.3) -> dict[str, Any]:
        """Returns parsed JSON object. Implementations must cache by input hash."""
        ...


def cache_key_for(provider: LLMProvider, system: str, user: str) -> str:
    return sha256_hex(f"{provider.model}|{PROMPT_VERSION}|{system}|{user}")


def extract_json(raw: str) -> dict[str, Any]:
    """Tolerant JSON extraction (handles ```json fences and stray prose)."""
    if not raw:
        raise LlmMalformedJson("empty response")
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LlmMalformedJson("no JSON object found")
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise LlmMalformedJson(str(e)) from e
    if not isinstance(obj, dict):
        raise LlmMalformedJson("response is not an object")
    return obj
