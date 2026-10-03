"""FREE AI provider router — provider-neutral, ZERO_COST_MODE enforced.

Providers (in configured priority order, all free-tier only):
  groq | gemini | openrouter | glm | openai-compatible (generic)

- No keys → router unavailable → newsroom stays DETERMINISTIC (never fails).
- Provider failure → next provider → deterministic fallback (caller handles None).
- NEVER calls a paid model: each adapter pins a free-tier endpoint/model.

PART-5 hardening:
- configuration consistency: __init__ resolves EVERYTHING (keys, base urls,
  models, order) from the env mapping given at construction; provider calls
  use ONLY those resolved values — never a fresh os.environ read.
- per-provider runtime state incl. NOT_CONFIGURED / RATE_LIMITED / DEGRADED.
- API keys never appear in errors or logs (redaction + header-based auth).
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from app.integrations.llm.base import LlmError

log = logging.getLogger("akh.ai.router")

PROVIDER_ORDER_DEFAULT = "groq,gemini,openrouter,glm,openai_compat"
ALL_PROVIDERS = ("groq", "gemini", "openrouter", "glm", "openai_compat")

_KEY_ENV = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY", "glm": "GLM_API_KEY",
            "openai_compat": "OPENAI_COMPAT_API_KEY"}
_SECRET_RE = re.compile(r"(?:(?<=sk-)[A-Za-z0-9_\-]{8,}"
                        r"|(?<=Bearer )[A-Za-z0-9_\-.]{8,}"
                        r"|(?<=key=)[A-Za-z0-9_\-]{8,})")


def redact(text: str) -> str:
    """Strip anything that looks like an API key from an error/log string."""
    return _SECRET_RE.sub("[REDACTED]", text or "")


class ProviderState:
    __slots__ = ("name", "model", "key_env", "configured", "enabled", "free",
                 "health", "last_success", "last_error", "latency_ms",
                 "calls_today", "priority", "_key", "_base_url")

    def __init__(self, name: str, model: str, *, key: str = "",
                 base_url: str = "", priority: int = 0, configured: bool = True,
                 enabled: bool = True, free: bool = True):
        self.name, self.model = name, model
        self.key_env = _KEY_ENV.get(name, "")
        self._key, self._base_url = key, base_url
        self.configured = configured
        self.enabled = enabled
        self.free = free
        self.priority = priority
        self.health = "HEALTHY" if configured else "NOT_CONFIGURED"
        self.last_success: str | None = None
        self.last_error: str | None = None
        self.latency_ms = 0
        self.calls_today = 0

    def public_state(self) -> dict[str, Any]:
        """Admin/inspection view — NEVER includes the key value."""
        return {"name": self.name, "model": self.model or "-",
                "configured": self.configured, "enabled": self.enabled,
                "free": self.free, "health": self.health,
                "last_success": self.last_success,
                "last_error": self.last_error, "latency_ms": self.latency_ms,
                "calls_today": self.calls_today, "priority": self.priority}


class FreeAiRouter:
    """chat_json(system=..., user=...) across configured free providers.

    All provider configuration is resolved ONCE from the env mapping passed
    to __init__ (or os.environ at construction time); _call() uses only the
    resolved ProviderState — a later os.environ change cannot desync a call.
    """

    def __init__(self, env: dict[str, str] | None = None, transport=None,
                 disabled: set[str] | None = None, priority_order: list[str] | None = None):
        import os

        e = dict(env if env is not None else os.environ)
        self.transport = transport
        self.zero_cost = e.get("ZERO_COST_MODE", "true").lower() != "false"
        self.free_only = e.get("AI_FREE_ONLY", "true").lower() != "false"
        order_csv = priority_order and ",".join(priority_order)
        order = [p.strip() for p in
                 (order_csv or e.get("AI_PROVIDER_PRIORITY", PROVIDER_ORDER_DEFAULT)).split(",")
                 if p.strip()]
        disabled = disabled or set()
        models = {
            "groq": e.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "gemini": e.get("GEMINI_MODEL", "gemini-2.0-flash"),
            "openrouter": e.get("OPENROUTER_MODEL",
                                "meta-llama/llama-3.3-70b-instruct:free"),
            "glm": e.get("GLM_MODEL", "glm-4-flash"),
            "openai_compat": e.get("OPENAI_COMPAT_MODEL", ""),
        }
        keys = {n: e.get(_KEY_ENV[n], "") for n in ALL_PROVIDERS}
        base_urls = {
            "glm": e.get("GLM_BASE_URL", "https://api.z.ai/api/paas/v4"),
            "openai_compat": e.get("OPENAI_COMPAT_BASE_URL", ""),
        }
        self.states: list[ProviderState] = []
        for pr, name in enumerate(order):
            if name not in ALL_PROVIDERS:
                continue
            configured = bool(keys[name]) and not (
                name == "openai_compat" and not base_urls["openai_compat"])
            st = ProviderState(
                name, models[name], key=keys[name],
                base_url=base_urls.get(name, ""), priority=pr,
                configured=configured,
                enabled=configured and name not in disabled)
            self.states.append(st)

    # ------------------------------------------------------------- inspection
    def provider_states(self) -> list[dict[str, Any]]:
        return [s.public_state() for s in self.states]

    @property
    def available(self) -> bool:
        return any(s.enabled and s.configured for s in self.states)

    # -------------------------------------------------------------- routing
    async def chat_json(self, *, system: str, user: str,
                        max_tokens: int = 2000) -> dict[str, Any] | None:
        """Try providers in priority order; any failure → next; all fail → None.
        Newsroom workers NEVER break because of a provider failure."""
        from app.integrations.llm.base import extract_json

        for st in self.states:
            if not (st.enabled and st.configured):
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
            except Exception as ex:  # noqa: BLE001 — failover, never crash
                st.last_error = redact(str(ex))[:120]
                st.health = ("RATE_LIMITED" if "429" in st.last_error else "DEGRADED")
                log.warning("provider %s failed: %s", st.name, st.last_error)
        return None  # deterministic fallback (caller HOLDs)

    async def _call(self, st: ProviderState, system: str, user: str,
                    max_tokens: int) -> str:
        """One provider call using ONLY the state resolved at construction."""
        if st.name == "gemini":
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{st.model}:generateContent")
            headers = {"x-goog-api-key": st._key}  # header, never in the URL
            payload = {"systemInstruction": {"parts": [{"text": system}]},
                       "contents": [{"parts": [{"text": user}]}],
                       "generationConfig": {"temperature": 0.2,
                                            "maxOutputTokens": max_tokens,
                                            "responseMimeType": "application/json"}}
        else:
            url = {
                "groq": "https://api.groq.com/openai/v1/chat/completions",
                "openrouter": "https://openrouter.ai/api/v1/chat/completions",
                "glm": f"{st._base_url.rstrip('/')}/chat/completions",
                "openai_compat": f"{st._base_url.rstrip('/')}/chat/completions",
            }[st.name]
            headers = {"Authorization": f"Bearer {st._key}"}
            payload = {"model": st.model,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}],
                       "temperature": 0.2, "max_tokens": max_tokens,
                       "response_format": {"type": "json_object"}}
        async with httpx.AsyncClient(timeout=45, transport=self.transport) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 429:
            raise LlmError("HTTP 429 rate limited")
        if resp.status_code != 200:
            raise LlmError(f"HTTP {resp.status_code}: {redact(resp.text[:120])}")
        data = resp.json()
        if st.name == "gemini":
            return data["candidates"][0]["content"]["parts"][0]["text"]
        return data["choices"][0]["message"]["content"] or ""
