#!/usr/bin/env python3
"""Verify external integrations with MINIMAL cost and NO secrets printed.

Run inside the container after credentials are placed in /opt/akhbot/.env:
    docker exec akhbot-app python /srv/scripts/verify_integrations.py

GLM:   one tiny chat request (max_tokens=16). Records provider/model/HTTP/latency.
TG:    getMe + getChat(staging) + sendMessage+deleteMessage round-trip.

On success writes settings keys (glm_verified_at / telegram_publish_verified_at)
which the admin dashboard uses to show LIVE_VERIFIED instead of merely CONFIGURED.
Exit code 0 = all configured integrations verified; 3 = none configured.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import time

import httpx

DATA_DIR = os.environ.get("DATA_DIR", "/data")


def env(key: str) -> str:
    return os.environ.get(key, "").strip()


def mark_setting(key: str, value: str) -> None:
    conn = sqlite3.connect(os.path.join(DATA_DIR, "akhbot.db"))
    with conn:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.close()


async def verify_glm() -> str:
    key, base, model = env("GLM_API_KEY"), env("GLM_BASE_URL"), env("GLM_MODEL")
    if not key:
        print("GLM: BLOCKED_EXTERNAL (no GLM_API_KEY)")
        return "BLOCKED_EXTERNAL"
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base.rstrip('/')}/chat/completions",
                headers={"Authorization": "Bearer {k}".format(k=key)},
                json={"model": model,
                      "messages": [{"role": "user", "content": "ping — reply with the single word: pong"}],
                      "max_tokens": 16},
            )
        latency_ms = int((time.monotonic() - t0) * 1000)
        if resp.status_code == 200:
            body = resp.json()
            usage = body.get("usage") or {}
            print(f"GLM: LIVE_VERIFIED provider=glm model={model} http=200 "
                  f"latency={latency_ms}ms tokens_in={usage.get('prompt_tokens', 'n/a')} "
                  f"tokens_out={usage.get('completion_tokens', 'n/a')}")
            mark_setting("glm_verified_at", f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}|{model}|{latency_ms}")
            return "LIVE_VERIFIED"
        print(f"GLM: ERROR http={resp.status_code} body={resp.text[:200]} (model={model})")
        mark_setting("glm_last_error", f"http {resp.status_code}")
        return "ERROR"
    except httpx.HTTPError as e:
        print(f"GLM: ERROR transport: {type(e).__name__}")
        mark_setting("glm_last_error", type(e).__name__)
        return "ERROR"


async def verify_telegram() -> str:
    token, chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_STAGING_CHAT_ID")
    if not (token and chat):
        print("TELEGRAM: BLOCKED_EXTERNAL (no TELEGRAM_BOT_TOKEN/TELEGRAM_STAGING_CHAT_ID)")
        return "BLOCKED_EXTERNAL"
    api = f"https://api.telegram.org/bot{token}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            t0 = time.monotonic()
            me = (await client.post(f"{api}/getMe")).json()
            if not me.get("ok"):
                print(f"TELEGRAM: ERROR getMe: {me.get('description', '?')}")
                return "ERROR"
            username = me["result"].get("username", "?")
            getch = (await client.post(f"{api}/getChat", json={"chat_id": chat})).json()
            if not getch.get("ok"):
                print(f"TELEGRAM: ERROR getChat({chat[:4]}…): {getch.get('description', '?')}")
                mark_setting("telegram_last_error", f"getChat: {getch.get('description', '')[:80]}")
                return "ERROR"
            # staging proof: post an explicit TEST message, edit it, then delete it
            sent = (await client.post(f"{api}/sendMessage", json={
                "chat_id": chat, "text": "[STAGING TEST] akhbot connectivity check — will be deleted"})).json()
            if not sent.get("ok"):
                print(f"TELEGRAM: ERROR sendMessage: {sent.get('description', '?')}")
                mark_setting("telegram_last_error", f"sendMessage: {sent.get('description', '')[:80]}")
                return "ERROR"
            mid = sent["result"]["message_id"]
            edited = (await client.post(f"{api}/editMessageText", json={
                "chat_id": chat, "message_id": mid,
                "text": "[STAGING TEST — EDITED] akhbot edit capability verified"})).json()
            deleted = (await client.post(f"{api}/deleteMessage", json={
                "chat_id": chat, "message_id": mid})).json()
        latency = int((time.monotonic() - t0) * 1000)
        ok_edit = bool(edited.get("ok"))
        ok_del = bool(deleted.get("ok"))
        status = "LIVE_VERIFIED" if (ok_edit and ok_del) else "PARTIAL"
        print(f"TELEGRAM: {status} bot=@{username} chat_id={chat[:4]}… post=ok edit={'ok' if ok_edit else 'FAIL'} "
              f"delete={'ok' if ok_del else 'FAIL'} latency={latency}ms")
        if status == "LIVE_VERIFIED":
            mark_setting("telegram_publish_verified_at",
                         time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        return status
    except httpx.HTTPError as e:
        print(f"TELEGRAM: ERROR transport: {type(e).__name__}")
        mark_setting("telegram_last_error", type(e).__name__)
        return "ERROR"


async def main() -> int:
    results = {"glm": await verify_glm(), "telegram": await verify_telegram()}
    if all(v == "BLOCKED_EXTERNAL" for v in results.values()):
        print("RESULT: nothing configured — add credentials to /opt/akhbot/.env first")
        return 3
    ok = all(v in ("LIVE_VERIFIED",) for k, v in results.items() if v != "BLOCKED_EXTERNAL")
    print("RESULT:", "ALL_VERIFIED" if ok else "INCOMPLETE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
