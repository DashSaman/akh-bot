"""T2 — Telethon realtime listener (production-capable, mock-tested).

Secrets only via env (TELEGRAM_INGEST_API_ID/_API_HASH/_SESSION) — never in
Git/logs/tests. When absent: status()=TELETHON_AUTH_REQUIRED and WEB_FALLBACK
stays authoritative. Dynamic monitored-source map refreshes from DB (≤60s).
Reconnect: bounded exponential backoff + jitter. Dedup with WEB_FALLBACK via
canonical external key (stable channel id + message id).
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

log = logging.getLogger("akh.ingest.telethon")

MAX_BACKOFF = 60.0
MAX_ATTEMPTS = 6
MAP_REFRESH_SECONDS = 60


def status(api_id: int | str = "", api_hash: str = "", session: str = "") -> str:
    vals = (api_id, api_hash, session)
    return "TELETHON_AUTH_REQUIRED" if not all(str(v or "").strip() for v in vals) else "CONFIGURED"


async def monitored_map(db, kind: str = "telegram") -> dict[int, str]:
    """OWNER_ENABLED telegram sources: source_id -> handle (dynamic; no hard-coding)."""
    rows = db.query(
        "SELECT id, external_id FROM sources WHERE platform=? AND enabled=1"
        " AND source_control_state='OWNER_ENABLED' AND COALESCE(external_id,'')!=''",
        (kind,))
    return {int(r["id"]): r["external_id"].lstrip("@") for r in rows}


class TelethonListener:
    """Persistent client wrapper. The real telethon import stays lazy so a missing
    package/creds can never crash other collectors (§20)."""

    def __init__(self, db, settings, client_factory=None) -> None:
        self.db = db
        self.settings = settings
        self._client: Any = None
        self._client_factory = client_factory  # injected mock in tests
        self._map: dict[int, str] = {}
        self._registered = False

    async def start(self) -> bool:
        st = status(self.settings.telegram_ingest_api_id,
                    self.settings.telegram_ingest_api_hash,
                    self.settings.telegram_ingest_session)
        if st != "CONFIGURED":
            log.info("telethon: %s (WEB_FALLBACK remains authoritative)", st)
            return False
        if self._client_factory is None:
            from telethon import TelegramClient
            from telethon.sessions import StringSession

            self._client_factory = lambda: TelegramClient(
                StringSession(self.settings.telegram_ingest_session),
                int(self.settings.telegram_ingest_api_id),
                self.settings.telegram_ingest_api_hash)
        backoff = 1.0
        attempts = 0
        while attempts < MAX_ATTEMPTS:
            attempts += 1
            try:
                client = self._client_factory()
                await client.connect()
                if not await client.is_user_authorized():
                    log.warning("telethon: not authorized — WEB_FALLBACK")
                    return False
                self._client = client
                self._map = await monitored_map(self.db)
                self._register_handlers()
                self._registered = True
                log.info("telethon: CONNECTED (%s sources)", len(self._map))
                return True
            except Exception as e:  # noqa: BLE001 — bounded reconnect §20
                delay = min(backoff, MAX_BACKOFF) * (0.7 + 0.6 * random.random())
                log.warning("telethon connect failed (%s); retry in %.1fs", e, delay)
                await asyncio.sleep(delay)
                backoff = min(backoff * 2, MAX_BACKOFF)
        return False  # bounded give-up: WEB_FALLBACK stays authoritative (§18/§20)

    def _register_handlers(self) -> None:
        from telethon import events

        client = self._client

        @client.on(events.NewMessage())
        async def _on_new(event):  # pragma: no cover — exercised via mock
            await self.handle_new(event)

        @client.on(events.MessageEdited())
        async def _on_edit(event):  # pragma: no cover
            await self.handle_edit(event)

        @client.on(events.Raw())
        async def _on_raw(event):  # pragma: no cover — deletions arrive raw
            name = type(event).__name__
            if "Delete" in name:
                await self.handle_delete(event)

    # ---- normalized handlers (pure; unit-tested with fakes) ----

    async def handle_new(self, event) -> dict[str, Any]:
        """NewMessage → identity resolve → persist RawItem → checkpoint → pipeline."""
        peer = getattr(event, "chat_id", None)
        sid0 = self.resolve_source(peer)
        if sid0 is not None:  # learn/refresh stable id for future handle changes
            self.db.execute("UPDATE sources SET tg_stable_id=? WHERE id=? AND (tg_stable_id IS NULL OR tg_stable_id!=?)",
                            (str(peer), sid0, str(peer)))
        from app.clustering.dedup import fingerprints_for
        from app.core.textnorm import detect_language
        from app.db.repo import RawItemsRepo

        peer = getattr(event, "chat_id", None) or getattr(getattr(event, "chat", None), "id", None)
        sid = self.resolve_source(peer, getattr(event.message, "chat", None))
        if sid is None:
            return {"action": "ignored", "reason": "SOURCE_NOT_IN_MAP"}
        msg = event.message
        text = msg.message or ""
        if not text:
            return {"action": "ignored", "reason": "NO_TEXT"}
        stable = self.stable_chat_key(peer)
        external_key = f"tg:{stable}:{msg.id}"  # canonical: SAME key-space guard as reconcile
        if RawItemsRepo(self.db).exists(sid, external_key):
            return {"action": "duplicate", "external_key": external_key}
        title = text.split("\n", 1)[0][:200]
        fp = fingerprints_for(f"https://t.me/{stable}/{msg.id}", title, text)
        fwd = getattr(msg, "forward", None)
        forward_from = str(getattr(fwd, "channel_id", None) or "") or None if fwd else None
        published = msg.date.isoformat(timespec="seconds") if msg.date else None
        item_id = RawItemsRepo(self.db).insert(
            source_id=sid, platform="telegram", external_key=external_key,
            url=f"https://t.me/{stable}/{msg.id}", title=title, text=text,
            language=detect_language(text), published_at=published,
            forward_from=forward_from,
            lineage_key=f"tg:{forward_from}" if forward_from else f"tg-self:{stable}",
            activation_ok=True, fingerprints=fp)
        from app.ingestion.checkpoints import advance_checkpoint

        advance_checkpoint(self.db, sid, remote_id=msg.id, item_id=item_id)
        return {"action": "stored", "item_id": item_id, "external_key": external_key}

    async def handle_edit(self, event) -> dict[str, Any]:
        """Edited message → revision under the SAME logical item (immutable evidence)."""
        from app.ingestion.telegram_ingest import apply_message_snapshot

        peer = getattr(event, "chat_id", None)
        sid = self.resolve_source(peer, None)
        if sid is None:
            return {"action": "ignored"}
        stable = self.stable_chat_key(peer)
        msg = event.message
        snap = {"chat_id": stable, "message_id": msg.id, "text": msg.message or "",
                "date": msg.date.isoformat(timespec="seconds") if msg.date else None,
                "edit_date": msg.edit_date.isoformat(timespec="seconds") if msg.edit_date else None,
                "forward_from": None}
        src = self.db.query_one("SELECT * FROM sources WHERE id=?", (sid,))
        out = apply_message_snapshot(self.db, src, snap)
        return {"action": out}

    async def handle_delete(self, event) -> dict[str, Any]:
        """Deletion → marker only; evidence kept; NO automatic public retraction (§15)."""
        ids = list(getattr(event, "messages", []) or [])
        peer = getattr(event, "channel_id", None) or getattr(event, "chat_id", None)
        sid = self.resolve_source(peer, None)
        stable = self.stable_chat_key(peer)
        marked = 0
        for mid in ids:
            self.db.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (f"src_deleted:{sid or 0}:{stable}:{mid}",
                 __import__("app.db.repo", fromlist=["utcnow"]).utcnow()))
            marked += 1
        return {"action": "deletion_marker", "count": marked,
                "review": True} if marked else {"action": "ignored"}

    def resolve_source(self, peer_id, chat=None) -> int | None:
        """§12 stable identity: tg_stable_id first, current-handle fallback.
        A handle change never creates a second logical source."""
        if peer_id is None:
            return None
        p = str(peer_id)
        digits = p.removeprefix("-100").lstrip("-")
        # stable ids stored on the source row
        row = self.db.query_one(
            "SELECT id FROM sources WHERE tg_stable_id IN (?, ?, ?) LIMIT 1",
            (p, digits, f"-100{digits}"))
        if row:
            return int(row["id"])
        for sid, handle in self._map.items():
            if p in (handle, f"@{handle}"):
                return sid
        return None

    def stable_chat_key(self, peer) -> str:
        return str(peer).removeprefix("-100")

    async def refresh_map(self) -> dict[int, str]:
        """§11: dynamic map — admin changes reflect without restart (≤60s)."""
        self._map = await monitored_map(self.db)
        return self._map

    async def run(self) -> None:
        ok = await self.start()
        if not ok:
            return
        while True:
            await asyncio.sleep(MAP_REFRESH_SECONDS)
            try:
                await self.refresh_map()
            except Exception:  # noqa: BLE001
                log.exception("map refresh failed; keeping previous map")
