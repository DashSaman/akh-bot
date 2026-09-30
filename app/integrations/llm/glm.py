"""Z.ai / GLM adapter (OpenAI-compatible chat/completions). Cached, retried, measured."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from app.db.repo import LlmCacheRepo
from app.integrations.llm.base import (
    LlmError,
    LlmMalformedJson,
    LlmTimeout,
    cache_key_for,
    extract_json,
)

log = logging.getLogger("akh.llm.glm")


class GlmProvider:
    name = "glm"

    def __init__(self, api_key: str, base_url: str, model: str,
                 cache: LlmCacheRepo | None = None, timeout: float = 90.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.cache = cache
        self.timeout = timeout
        self.transport = transport  # injected in tests

    async def chat_json(self, *, system: str, user: str, max_tokens: int = 4000,
                        temperature: float = 0.3) -> dict[str, Any]:
        key = cache_key_for(self, system, user)  # type: ignore[arg-type]
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit:
                return json.loads(hit["response_json"])

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        started = time.monotonic()
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout, transport=self.transport
                ) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions", json=body, headers=headers
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    raw = data["choices"][0]["message"]["content"] or ""
                    parsed = extract_json(raw)
                    usage = data.get("usage") or {}
                    if self.cache is not None:
                        self.cache.put(
                            key, json.dumps(parsed, ensure_ascii=False), self.model,
                            data.get("model", self.model),
                            int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)),
                            int((time.monotonic() - started) * 1000),
                        )
                    return parsed
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_err = LlmError(f"HTTP {resp.status_code}")
                else:
                    raise LlmError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            except (httpx.TimeoutException, asyncio.TimeoutError) as e:
                last_err = LlmTimeout(str(e))
            except httpx.HTTPError as e:
                last_err = LlmError(str(e))
            await asyncio.sleep(min(2**attempt, 8))
        raise last_err or LlmError("unknown")


class FakeProvider:
    """Deterministic provider for tests. Scripted by (prompt_kind, n) call sequence."""

    name = "fake"
    model = "fake-model"
    KIND_MARKERS = {
        "claims": "CLAIM-EXTRACTION",
        "writer": "NEWSROOM-WRITER",
    }

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict[str, str]] = []

    async def chat_json(self, *, system: str, user: str, max_tokens: int = 4000,
                        temperature: float = 0.3) -> dict[str, Any]:
        self.calls.append({"system": system, "user": user})
        kind = "writer"
        for k, marker in self.KIND_MARKERS.items():
            if marker in system:
                kind = k
        for i, r in enumerate(self.responses):
            if r.get("__kind__") == kind:
                self.responses.pop(i)
                if r.get("__error__"):
                    raise r["__error__"]
                return {k: v for k, v in r.items() if not k.startswith("__")}
        if self.responses and "__error__" in self.responses[0]:
            e = self.responses.pop(0)["__error__"]
            raise e
        raise LlmMalformedJson("fake provider exhausted")
