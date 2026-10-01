"""FREE AI provider router — provider-neutral, ZERO_COST_MODE enforced.

Providers (in configured priority order, all free-tier only):
  groq | gemini | openrouter | glm | openai-compatible (generic)

- No keys → router unavailable → newsroom stays DETERMINISTIC (never fails).
- Provider failure → next provider → deterministic fallback (caller handles None).
- NEVER calls a paid model: each adapter pins a free-tier endpoint/model.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from app.integrations.llm.base import LlmError

log = logging.getLogger("akh.ai.router")

PROVIDER_ORDER_DEFAULT = "groq,gemini,openrouter,glm,openai_compat"


class ProviderState:
    __slots__ = ("name", "model", "enabled", "health", "last_success", "last_error",
                 "latency_ms", "calls_today", "free")

    def __init__(self, name: str, model: str, free: bool = True):
        self.name, self.model, self.free = name, model, free
        self.enabled = True
        self.health = "HEALTHY"
        self.last_success: str | None = None
        self.last_error: str | None = None
        self.latency_ms = 0
        self.calls_today = 0


class FreeAiRouter:
    """chat_json(system=..., user=...) across configured free providers.

    Usage: router = FreeAiRouter(os.environ); result = await router.chat_json(...)
    Returns dict OR None when every provider is unavailable (deterministic mode).
    """

    def __init__(self, env: dict[str, str] | None = None, transport=None):
        e = env if env is not None else dict(os.environ)
        self.transport = transport
        self.zero_cost = e.get("ZERO_COST_MODE", "true").lower() != "false"
        self.free_only = e.get("AI_FREE_ONLY", "true").lower() != "false"
        order = [p.strip() for p in e.get("AI_PROVIDER_PRIORITY", PROVIDER_ORDER_DEFAULT).split(",") if p.strip()]
        self.states: list[ProviderState] = []
        creds = {
            "groq": ("llama-3.3-70b-versatile", e.get("GROQ_API_KEY", "")),
            "gemini": ("gemini-2.0-flash", e.get("GEMINI_API_KEY", "")),
            "openrouter": ("meta-llama/llama-3.3-70b-instruct:free", e.get("OPENROUTER_API_KEY", "")),
            "glm": (e.get("GLM_MODEL", "glm-4-flash"), e.get("GLM_API_KEY", "")),
            "openai_compat": (e.get("OPENAI_COMPAT_MODEL", ""), e.get("OPENAI_COMPAT_API_KEY", "")),
        }
        for name in order:
            model, key = creds.get(name, ("", ""))
            if not key or (name == "openai_compat" and not e.get("OPENAI_COMPAT_BASE_URL")):
                continue
            st = ProviderState(name, model)
            if e.get(f"AI_{name.upper()}_DISABLED") == "1":
                st.enabled = False
            self.states.append(st)
        if self.free_only:
            for st in self.states:
                st.free = True  # all configured adapters are free-tier pinned

    @property
    def available(self) -> bool:
        return any(s.enabled for s in self.states)

    async def chat_json(self, *, system: str, user: str, max_tokens: int = 2000) -> dict[str, Any] | None:
        from app.integrations.llm.base import extract_json

        for st in self.states:
            if not st.enabled:
                continue
            try:
                t0 = time.monotonic()
                raw = await self._call(st, system, user, max_tokens)
                parsed = extract_json(raw)
                st.health, st.last_error = "HEALTHY", None
                st.last_success = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                st.latency_ms = int((time.monotonic() - t0) * 1000)
                st.calls_today += 1
                return parsed
            except (LlmError, httpx.HTTPError, Exception) as ex:  # noqa: BLE001 — failover
                st.health = "DEGRADED"
                st.last_error = str(ex)[:120]
                log.warning("provider %s failed: %s", st.name, st.last_error)
        return None  # deterministic fallback

    async def _call(self, st: ProviderState, system: str, user: str, max_tokens: int) -> str:
        headers, url, payload = {}, "", {}
        if st.name in ("groq", "openrouter", "glm", "openai_compat"):
            if st.name == "groq":
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": "Bearer {k}"}
            elif st.name == "openrouter":
                url = "https://openrouter.ai/api/v1/chat/completions"
            elif st.name == "glm":
                url = f"{os.environ.get('GLM_BASE_URL', 'https://api.z.ai/api/paas/v4')}/chat/completions"
            else:
                url = f"{os.environ['OPENAI_COMPAT_BASE_URL'].rstrip('/')}/chat/completions"
            headers = {"Authorization": "Bearer " + os.environ.get(_key_of(st.name), "")}
            payload = {"model": st.model,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}],
                       "temperature": 0.2, "max_tokens": max_tokens,
                       "response_format": {"type": "json_object"}}
        elif st.name == "gemini":
            url = ("https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{st.model}:generateContent?key=" + os.environ.get("GEMINI_API_KEY", ""))
            payload = {"systemInstruction": {"parts": [{"text": system}]},
                       "contents": [{"parts": [{"text": user}]}],
                       "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens,
                                            "responseMimeType": "application/json"}}
        async with httpx.AsyncClient(timeout=45, transport=self.transport) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            raise LlmError(f"HTTP {resp.status_code}: {resp.text[:120]}")
        data = resp.json()
        if st.name == "gemini":
            return data["candidates"][0]["content"]["parts"][0]["text"]
        return data["choices"][0]["message"]["content"] or ""


def _key_of(name: str) -> str:
    return {"groq": "GROQ_API_KEY", "openrouter": "OPENROUTER_API_KEY",
            "glm": "GLM_API_KEY", "openai_compat": "OPENAI_COMPAT_API_KEY"}.get(name, "")
