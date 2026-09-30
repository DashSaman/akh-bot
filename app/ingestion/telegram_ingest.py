"""Telegram channel ingestion via Telethon (dedicated listener account).

Statuses: NOT_CONFIGURED / WAITING_FOR_AUTH / CONNECTED / ERROR.
Telethon is imported lazily so a missing session disables this adapter cleanly.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.clustering.dedup import fingerprints_for
from app.core.textnorm import detect_language
from app.db.repo import RawItemsRepo, SourcesRepo, parse_iso

log = logging.getLogger("akh.ingest.telegram")


class TelegramIngestor:
    def __init__(self, api_id: int, api_hash: str, session: str) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.session = session
        self._client: Any = None

    def status(self) -> str:
        if not (self.api_id and self.api_hash and self.session):
            return "NOT_CONFIGURED"
        return "CONNECTED" if self._client else "WAITING_FOR_AUTH"

    async def _ensure_client(self) -> Any:
        if self._client:
            return self._client
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(StringSession(self.session), self.api_id, self.api_hash)
        await client.connect()  # type: ignore[attr-defined]
        if not await client.is_user_authorized():  # type: ignore[attr-defined]
            return None
        self._client = client
        return client

    async def reconcile_source(self, source: dict[str, Any], db: Any, limit: int = 50) -> dict[str, Any]:
        items = RawItemsRepo(db)
        sources = SourcesRepo(db)
        summary = {"source_id": source["id"], "new": 0, "skipped": 0}
        client = await self._ensure_client()
        if client is None:
            sources.mark_fetch(source["id"], False, "telethon not authorized (WAITING_FOR_AUTH)")
            summary["error"] = "WAITING_FOR_AUTH"
            return summary
        from telethon.tl.types import PeerChannel

        activated = parse_iso(source["activated_at"])
        entity = await client.get_entity(source["external_id"] or source["url"])  # type: ignore[attr-defined]
        async for msg in client.iter_messages(entity, limit=limit):  # type: ignore[attr-defined]
            external_key = f"tg:{msg.chat_id}:{msg.id}"
            if items.exists(source["id"], external_key):
                summary["skipped"] += 1
                continue
            text = msg.message or ""
            if not text:
                continue
            published = msg.date.astimezone(timezone.utc) if msg.date else None
            activation_ok = bool(
                activated is None or (published and published >= activated)
            )
            forward_from = None
            if getattr(msg, "forward", None):
                fwd = msg.forward
                forward_from = (
                    str(getattr(fwd, "channel_id", None) or getattr(fwd, "from_id", None) or "")
                    or None
                )
            title = text.split("\n", 1)[0][:200]
            fp = fingerprints_for("", title, text)
            fwd_lineage = f"tg:{forward_from}" if forward_from else f"tg-self:{source['external_id']}"
            items.insert(
                source_id=source["id"], platform="telegram", external_key=external_key,
                title=title, text=text, language=detect_language(text),
                published_at=published.isoformat(timespec="seconds") if published else None,
                edited_at=msg.edit_date.isoformat(timespec="seconds") if msg.edit_date else None,
                forward_from=forward_from, lineage_key=fwd_lineage,
                activation_ok=activation_ok, fingerprints=fp,
            )
            summary["new"] += 1
        sources.mark_fetch(source["id"], True)
        return summary


def telegram_signature(brand_name: str) -> str:
    return f"— {brand_name}"


def apply_message_snapshot(db: Any, source: dict[str, Any], msg: dict[str, Any]) -> str:
    """Pure helper (unit-testable): stores/updates one telegram message snapshot.

    msg: {chat_id, message_id, text, date(iso), edit_date(iso|None), forward_from}
    Returns "stored" | "duplicate" | "revised".
    """
    items = RawItemsRepo(db)
    external_key = f"tg:{msg['chat_id']}:{msg['message_id']}"
    fp = fingerprints_for("", msg["text"].split("\n", 1)[0][:200], msg["text"])
    existing = items.db.query_one(
        "SELECT * FROM raw_items WHERE source_id=? AND external_key=?",
        (source["id"], external_key),
    )
    activated = parse_iso(source["activated_at"])
    published = parse_iso(msg.get("date"))
    if existing:
        if fp["content_hash"] != items.db.query_one(
            "SELECT content_hash FROM item_revisions WHERE raw_item_id=? ORDER BY rev_no DESC LIMIT 1",
            (existing["id"],),
        )["content_hash"]:
            items.add_revision(
                existing["id"], msg["text"].split("\n", 1)[0][:200], msg["text"],
                fp["content_hash"], msg.get("edit_date"),
            )
            items.db.execute(
                "UPDATE raw_items SET edited_at=?, text=? WHERE id=?",
                (msg.get("edit_date"), msg["text"], existing["id"]),
            )
            return "revised"
        return "duplicate"
    activation_ok = bool(
        activated is None or (published is not None and published >= activated)
    )
    fwd = msg.get("forward_from")
    lineage = f"tg:{fwd}" if fwd else f"tg-self:{source['external_id'] or source['id']}"
    title = msg["text"].split("\n", 1)[0][:200]
    items.insert(
        source_id=source["id"], platform="telegram", external_key=external_key,
        title=title, text=msg["text"], language=detect_language(msg["text"]),
        published_at=msg.get("date"), edited_at=msg.get("edit_date"),
        forward_from=fwd, lineage_key=lineage, activation_ok=activation_ok,
        fingerprints=fp,
    )
    return "stored"
