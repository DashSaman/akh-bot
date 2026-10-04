"""Multi-admin Telegram editorial intake (Part E, directive 2026-10-04).

Every admin submission becomes a RawItem in MANUAL_HOLD and enters the SAME
canonical pipeline (dedup -> Event -> verification -> Story -> publication)
after explicit approval — there is NO direct-send path. Auth is by immutable
numeric Telegram user_id (bot_admins table). Feature flag
EDITORIAL_BOT_INTAKE_ENABLED=false leaves production untouched; the poller
then never even calls getUpdates.

Media policy (E11): Telegram file_id reuse only; no permanent binaries; the
canonical media ladder degrades to text-only on failure. Forwarded items map
their canonical source identity when known; unknown forward origins never
increase the independent-confirmation count.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

log = logging.getLogger("akh.editorial.intake")

MANUAL_IDENTITY = "ManualEditorial"
_OFFSET_KEY = "telegram_intake_offset"
_DENY_TEXT = "⛔ شما مجاز به ارسال خبر به راسته نیستید."
_PENDING_EDIT: dict[str, tuple[float, int]] = {}  # chat_id -> (ts, submission_id)
_ALBUM_TASKS: dict[str, Any] = {}                  # group -> debounce task
_ALBUM_DEBOUNCE_S = 2.0                            # quiet window per album


async def _album_debounce(db, api, group: str) -> None:
    await asyncio.sleep(_ALBUM_DEBOUNCE_S)
    await _album_finalize(db, api, group)


async def _album_finalize(db, api, group: str) -> None:
    """Runs ALBUM_DEBOUNCE_S after the LAST album item: sends the single
    preview for the whole media group (order preserved in raw_items)."""
    _ALBUM_TASKS.pop(group, None)
    row = db.query_one(
        "SELECT s.* FROM manual_submissions s"
        " WHERE s.telegram_media_group_id=? ORDER BY s.id DESC LIMIT 1",
        (group,))
    if not row or row["status"] != "RECEIVED":
        return  # already finalized / cancelled
    db.execute("UPDATE manual_submissions SET status='PREVIEW' WHERE id=?",
               (row["id"],))
    item = db.query_one("SELECT title, forward_from, media_json FROM raw_items"
                        " WHERE id=?", (row["raw_item_id"],))
    try:
        refs = json.loads(item["media_json"] or "[]")
    except (ValueError, TypeError):
        refs = []
    await _send_preview_via(api, row["telegram_chat_id"], row["id"],
                            item["title"] or "آلبوم رسانه‌ای",
                            item["forward_from"] or "آلبوم", refs)


async def _send_preview_via(api, chat_id: str, sid: int, title: str,
                            origin: str, refs: list) -> None:
    kb = {"inline_keyboard": [[
        {"text": "🚀 انتشار", "callback_data": f"cb:{sid}:publish"},
        {"text": "🔎 بررسی و انتشار", "callback_data": f"cb:{sid}:review"},
    ], [
        {"text": "✏️ ویرایش", "callback_data": f"cb:{sid}:edit"},
        {"text": "❌ لغو", "callback_data": f"cb:{sid}:cancel"},
    ]]}
    media_note = (f"\n📎 رسانه: {len(refs)} فایل (file_id — بدون ذخیره دائمی)"
                  if refs else "")
    res = await api("sendMessage", {
        "chat_id": chat_id,
        "text": (f"📰 پیش‌نمایش راسته\n\n{title}\n\n"
                 f"منبع: {origin}\nوضعیت: در انتظار تأیید تحریریه{media_note}"),
        "reply_markup": kb})
    if res and res.get("ok"):
        pmid = res.get("result", {}).get("message_id")
        db_exec = _DB_EXEC_HOLDER[0]
        db_exec("UPDATE manual_submissions SET preview_message_id=? WHERE id=?",
                (str(pmid), sid))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_DB_EXEC_HOLDER: list = [None]  # bound at worker start for finalize helpers


class EditorialIntake:
    """Long-poll worker; persisted update offset; restart safe (E5)."""

    def __init__(self, db, settings) -> None:
        self.db = db
        self.settings = settings
        _DB_EXEC_HOLDER[0] = db.execute
        self._base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    # ------------------------------------------------------------- telegram
    async def _api(self, method: str, payload: dict[str, Any]) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=40) as client:
                r = await client.post(f"{self._base}/{method}", json=payload)
                return r.json()
        except Exception as ex:  # noqa: BLE001 — poller must never die
            log.warning("intake api %s failed: %s", method, str(ex)[:120])
            return None

    # ------------------------------------------------------------- lifecycle
    async def loop(self) -> None:
        while True:
            try:
                if not getattr(self.settings, "editorial_bot_intake_enabled",
                                False):
                    await asyncio.sleep(30)
                    continue
                offset = self._load_offset()
                data = await self._api("getUpdates", {
                    "offset": (offset + 1) if offset else None,
                    "timeout": 25, "limit": 20,
                    "allowed_updates": ["message", "callback_query"]})
                if not data or not data.get("ok"):
                    await asyncio.sleep(5)
                    continue
                for upd in data.get("result", []):
                    self._save_offset(int(upd["update_id"]))
                    try:
                        await self._dispatch(upd)
                    except Exception:  # noqa: BLE001
                        log.exception("intake dispatch failed update=%s",
                                      upd.get("update_id"))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("intake loop error")
                await asyncio.sleep(10)

    def _load_offset(self) -> int:
        from app.db.repo import SettingsRepo
        v = SettingsRepo(self.db).get(_OFFSET_KEY) or ""
        try:
            return int(v)
        except ValueError:
            return 0

    def _save_offset(self, update_id: int) -> None:
        from app.db.repo import SettingsRepo
        SettingsRepo(self.db).set(_OFFSET_KEY, str(update_id))

    # ------------------------------------------------------------- dispatch
    async def _dispatch(self, upd: dict[str, Any]) -> None:
        if "callback_query" in upd:
            await self._on_callback(upd["callback_query"])
            return
        msg = upd.get("message") or {}
        if not msg:
            return
        chat_id = str(msg.get("chat", {}).get("id", ""))
        admin = self._auth(msg)
        if not admin:
            await self._api("sendMessage", {"chat_id": chat_id,
                                            "text": _DENY_TEXT})
            return
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if text.startswith("/"):
            await self._on_command(admin, chat_id, text)
            return
        await self._on_submission(admin, msg, chat_id)

    # ------------------------------------------------------------------ auth
    def _auth(self, msg: dict[str, Any]) -> dict | None:
        uid = str((msg.get("from") or {}).get("id") or "")
        if not uid:
            return None
        row = self.db.query_one(
            "SELECT * FROM bot_admins WHERE telegram_user_id=? AND enabled=1"
            " AND can_submit=1", (uid,))
        return row

    def _can(self, admin: dict, perm: str) -> bool:
        return bool(admin.get(perm)) or admin.get("role") == "OWNER"

    # --------------------------------------------------------------- commands
    async def _on_command(self, admin: dict, chat_id: str, text: str) -> None:
        parts = text.split()
        cmd = parts[0].split("@")[0].lower()
        if cmd in ("/start", "/help"):
            await self._api("sendMessage", {"chat_id": chat_id, "text":
                "📰 تحریریه راسته — خبر/فوروارد/عکس/ویدیو بفرستید؛ "
                "همه از همان خط تولید استاندارد عبور می‌کنند."})
            return
        if not self._can(admin, "can_manage_admins"):
            await self._api("sendMessage", {"chat_id": chat_id,
                                            "text": "⛔ دسترسی مدیریتی ندارید."})
            return
        if cmd == "/admins":
            rows = self.db.query("SELECT * FROM bot_admins ORDER BY id")
            lines = ["%s `%s` %s %s" % (r["telegram_user_id"], r["role"],
                                        "✅" if r["enabled"] else "⛔",
                                        r["display_name"][:20]) for r in rows]
            await self._api("sendMessage", {"chat_id": chat_id,
                "text": "مدیران:\n" + "\n".join(lines) or "-"})
            return
        if cmd == "/addadmin" and len(parts) >= 2:
            role = (parts[2].upper()
                    if len(parts) > 2 and
                    parts[2].upper() in ("EDITOR", "PUBLISHER") else "EDITOR")
            self.db.execute(
                "INSERT OR IGNORE INTO bot_admins (telegram_user_id, role,"
                " can_manage_admins, created_by, created_at, updated_at)"
                " VALUES (?, ?, 0, ?, ?, ?)",
                (parts[1], role, admin["telegram_user_id"], _now(), _now()))
            await self._api("sendMessage", {"chat_id": chat_id,
                "text": f"✅ ادمین {parts[1]} ({role}) اضافه شد."})
            return
        if cmd == "/disableadmin" and len(parts) >= 2:
            self.db.execute("UPDATE bot_admins SET enabled=0, updated_at=?"
                            " WHERE telegram_user_id=?", (_now(), parts[1]))
            await self._api("sendMessage", {"chat_id": chat_id,
                "text": f"⛔ ادمین {parts[1]} غیرفعال شد."})
            return
        await self._api("sendMessage", {"chat_id": chat_id,
                                        "text": "فرمان ناشناخته."})

    # ----------------------------------------------------------- submissions
    def _ensure_manual_source(self) -> int:
        row = self.db.query_one(
            "SELECT id FROM sources WHERE identity=?", (MANUAL_IDENTITY,))
        if row:
            return row["id"]
        self.db.execute(
            "INSERT INTO sources (name, platform, external_id, url, language,"
            " category, source_type, status, enabled, priority, notes,"
            " created_at, identity, verification_allowed,"
            " can_increase_independent_count)"
            " VALUES ('Manual Editorial Submission', 'telegram', ?, '', 'fa',"
            " 'manual', 'direct', 'APPROVED', 1, 90,"
            " 'admin submissions; verification_allowed=0 (E8)', ?, ?, 0, 0)",
            (MANUAL_IDENTITY, _now(), MANUAL_IDENTITY))
        return self.db.query_one(
            "SELECT id FROM sources WHERE identity=?", (MANUAL_IDENTITY,))["id"]

    def _map_forward_source(self, msg: dict[str, Any]) -> tuple[int, str]:
        """(source_id, reported_origin). Known canonical identity maps to its
        source row; unknown origins stay on the manual source and NEVER add
        independent confirmations (E7)."""
        origin = msg.get("forward_origin") or {}
        chat = {}
        if origin.get("type") in ("channel", "chat"):
            chat = origin.get("chat") or {}
        legacy = msg.get("forward_from_chat") or {}
        title = chat.get("title") or legacy.get("title") or ""
        username = chat.get("username") or legacy.get("username") or ""
        if origin.get("type") == "user":
            title = ((origin.get("sender_user") or {})
                     .get("first_name", "")) or title
        person = msg.get("forward_from") or {}
        title = title or (person.get("first_name") or "")
        username = username or (person.get("username") or "")
        if title or username:
            for pat in (username.lstrip("@"), title):
                if not pat:
                    continue
                row = self.db.query_one(
                    "SELECT id FROM sources WHERE (identity=? OR name LIKE ?"
                    " OR url LIKE ?) AND status != 'LIMITED_X_ACCESS'"
                    " ORDER BY identity != '' DESC LIMIT 1",
                    (pat, f"%{pat}%", f"%{pat}%"))
                if row:
                    return row["id"], (title or f"@{username}")
        reported = title or (f"@{username}" if username else "منبع ناشناس")
        return self._ensure_manual_source(), reported

    def _media_refs(self, msg: dict[str, Any]) -> list[dict[str, str]]:
        refs: list[dict[str, str]] = []
        if msg.get("photo"):
            refs.append({"type": "photo",
                         "file_id": msg["photo"][-1]["file_id"]})
        if msg.get("video"):
            refs.append({"type": "video",
                         "file_id": msg["video"]["file_id"]})
        doc = msg.get("document") or {}
        if doc and str(doc.get("mime", "")).startswith(("image/", "video/")):
            refs.append({"type": "video" if doc["mime"].startswith("video/")
                         else "photo", "file_id": doc["file_id"]})
        return refs

    async def _on_submission(self, admin: dict, msg: dict[str, Any],
                             chat_id: str) -> None:
        text = (msg.get("text") or msg.get("caption") or "").strip()
        mid = str(msg.get("message_id", ""))
        group = str(msg.get("media_group_id") or "")
        # pending ✏️ edit flow: this text replaces the last submission body
        pend = _PENDING_EDIT.get(chat_id)
        if pend and text and not self._media_refs(msg):
            _PENDING_EDIT.pop(chat_id, None)
            if (datetime.now(timezone.utc).timestamp() - pend[0]) < 300:
                self.db.execute(
                    "UPDATE raw_items SET text=?, title=? WHERE id=("
                    " SELECT raw_item_id FROM manual_submissions WHERE id=?)",
                    (text, text.splitlines()[0][:140] if text else "", pend[1]))
                await self._api("sendMessage", {"chat_id": chat_id,
                    "text": "✏️ متن به‌روزرسانی شد و پیش از انتشار دوباره بررسی می‌شود."})
                return
        src_id, origin = self._map_forward_source(msg)
        refs = self._media_refs(msg)
        if not text and not refs:
            await self._api("sendMessage", {"chat_id": chat_id,
                "text": "⚠️ محتوایی قابل پردازش نبود (فقط متن/عکس/ویدیو)."})
            return
        title = (text.splitlines()[0][:140] if text else
                 (f"‎رسانه فوروارد‌شده از {origin}")[:140])
        # album: one RawItem for the whole group; preview only after the
        # debounce window is quiet (§6) — order preserved, no fragments.
        if group:
            row = self.db.query_one(
                "SELECT s.raw_item_id rid, s.status st FROM manual_submissions s"
                " WHERE s.telegram_media_group_id=? ORDER BY s.id DESC LIMIT 1",
                (group,))
            if row and row["rid"]:
                cur = self.db.query_one(
                    "SELECT media_json FROM raw_items WHERE id=?", (row["rid"],))
                try:
                    media = json.loads(cur["media_json"] or "[]")
                except (ValueError, TypeError):
                    media = []
                media.extend(refs)
                if text:
                    self.db.execute("UPDATE raw_items SET text=?, title=?"
                                    " WHERE id=?",
                                    (text, title, row["rid"]))
                self.db.execute("UPDATE raw_items SET media_json=? WHERE id=?",
                                (json.dumps(media, ensure_ascii=False),
                                 row["rid"]))
                task = _ALBUM_TASKS.get(group)
                if task and not task.done():
                    task.cancel()
                _ALBUM_TASKS[group] = asyncio.get_running_loop().create_task(
                    _album_debounce(self.db, self._api, group))
                return
        lang = "fa" if any("\u0600" <= c <= "\u06FF" for c in text) else "und"
        self.db.execute(
            "INSERT INTO raw_items (source_id, platform, external_key, url,"
            " title, text, language, author, published_at, fetched_at,"
            " forward_from, media_json, activation_ok, processed_state)"
            " VALUES (?, 'telegram', ?, '', ?, ?, ?, ?, ?, ?, ?, ?, 0,"
            " 'NEW')",
            (src_id, f"manual:{chat_id}:{mid}", title, text, lang,
             admin["display_name"] or admin["telegram_user_id"],
             _now(), _now(), origin, json.dumps(refs, ensure_ascii=False)))
        rid = self.db.query_one("SELECT MAX(id) id FROM raw_items")["id"]
        self.db.execute(
            "INSERT INTO manual_submissions (submitter_admin_id,"
            " telegram_chat_id, telegram_message_id, telegram_media_group_id,"
            " forwarded_origin, raw_item_id, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'RECEIVED', ?)",
            (admin["id"], chat_id, mid, group, origin, rid, _now()))
        sid = self.db.query_one("SELECT MAX(id) id FROM manual_submissions")["id"]
        if group:
            # first fragment: leave RECEIVED; the debounce finalizer previews
            _ALBUM_TASKS[group] = asyncio.get_running_loop().create_task(
                _album_debounce(self.db, self._api, group))
            return
        self.db.execute("UPDATE manual_submissions SET status='PREVIEW'"
                        " WHERE id=?", (sid,))
        await self._send_preview(chat_id, sid, title, origin, refs, admin)

    async def _send_preview(self, chat_id: str, sid: int, title: str,
                            origin: str, refs: list, admin: dict) -> None:
        kb = {"inline_keyboard": [[
            {"text": "🚀 انتشار", "callback_data": f"cb:{sid}:publish"},
            {"text": "🔎 بررسی و انتشار", "callback_data": f"cb:{sid}:review"},
        ], [
            {"text": "✏️ ویرایش", "callback_data": f"cb:{sid}:edit"},
            {"text": "❌ لغو", "callback_data": f"cb:{sid}:cancel"},
        ]]}
        media_note = f"\n📎 رسانه: {len(refs)} فایل (file_id — بدون ذخیره دائمی)" if refs else ""
        res = await self._api("sendMessage", {"chat_id": chat_id,
            "text": (f"📰 پیش‌نمایش راسته\n\n{title}\n\n"
                     f"منبع: {origin}\nوضعیت: در انتظار تأیید تحریریه"
                     f"{media_note}"),
            "reply_markup": kb})
        if res and res.get("ok"):
            pmid = res.get("result", {}).get("message_id")
            self.db.execute("UPDATE manual_submissions SET preview_message_id=?"
                            " WHERE id=?", (str(pmid), sid))

    # -------------------------------------------------------------- callbacks
    async def _on_callback(self, cb: dict[str, Any]) -> None:
        await self._api("answerCallbackQuery",
                        {"callback_query_id": cb["id"]})
        uid = str((cb.get("from") or {}).get("id") or "")
        admin = self.db.query_one(
            "SELECT * FROM bot_admins WHERE telegram_user_id=? AND enabled=1",
            (uid,))
        chat_id = str((cb.get("message") or {}).get("chat", {}).get("id", ""))
        data = cb.get("data") or ""
        try:
            _, sid_s, action = data.split(":")
            sid = int(sid_s)
        except ValueError:
            return
        sub = self.db.query_one("SELECT * FROM manual_submissions WHERE id=?",
                                (sid,))
        if not sub or not admin:
            return
        if action in ("publish", "review") and self._can(admin, "can_publish"):
            self.db.execute("UPDATE raw_items SET activation_ok=1,"
                            " processed_state='NEW' WHERE id=?",
                            (sub["raw_item_id"],))
            self.db.execute(
                "UPDATE manual_submissions SET status='SUBMITTED',"
                " approved_at=? WHERE id=?", (_now(), sid))
            await self._api("sendMessage", {"chat_id": chat_id,
                "text": "🚀 وارد خط تولید استاندارد شد (دداپ/رویداد/تأیید/"
                        "انتشار همان مسیر خودکار)."})
        elif action == "edit":
            if not self._can(admin, "can_edit"):
                await self._api("sendMessage", {"chat_id": chat_id,
                    "text": "⛔ مجوز ویرایش ندارید."})
                return
            _PENDING_EDIT[chat_id] = (datetime.now(timezone.utc).timestamp(), sid)
            await self._api("sendMessage", {"chat_id": chat_id,
                "text": "✏️ متن اصلاح‌شده را همین‌جا بفرستید (تا ۵ دقیقه)."})
        elif action == "cancel" and self._can(admin, "can_cancel"):
            self.db.execute("UPDATE raw_items SET activation_ok=0,"
                            " processed_state='ERROR' WHERE id=?",
                            (sub["raw_item_id"],))
            self.db.execute("UPDATE manual_submissions SET status='CANCELLED'"
                            " WHERE id=?", (sid,))
            await self._api("sendMessage", {"chat_id": chat_id,
                                            "text": "❌ لغو شد."})


def bootstrap_owner(db, settings) -> bool:
    """E3: seed the OWNER admin from the safe existing configuration
    (TELEGRAM_ADMIN_CHAT_ID is the owner's private user chat) — never guessed
    from usernames."""
    owner = str(getattr(settings, "newsroom_owner_telegram_id", "") or
                getattr(settings, "telegram_admin_chat_id", "") or "").strip()
    if not owner.lstrip("-").isdigit() or owner.startswith("-"):
        return False
    db.execute(
        "INSERT OR IGNORE INTO bot_admins (telegram_user_id, display_name,"
        " role, enabled, can_submit, can_publish, can_edit, can_cancel,"
        " can_manage_admins, created_by, created_at, updated_at)"
        " VALUES (?, 'Owner', 'OWNER', 1, 1, 1, 1, 1, 1, 'bootstrap', ?, ?)",
        (owner, _now(), _now()))
    return True
