"""Self-service source management (owner directive 2026-10-04 §SRC).

Dynamic, database-driven: add/enable/disable take effect on the NEXT
scheduler cycle with NO restart — the scheduler already re-reads the
sources table every pass; publication-time checks re-read current state
(disabled sources cannot send queued jobs — see can_publish_now()).

Normalization + SSRF guard: only https/http and public Telegram handles are
accepted; private RFC1918/loopback/metadata targets and non-web schemes are
rejected BEFORE any fetch. Duplicate protection: exact-URL endpoints are
rejected (existing id returned) and same-canonical-identity endpoints are
attached to that identity so they count as ONE independent source.

Priority != trust: polling priority (VERY_HIGH..LOW) touches only scheduling
order/frequency — verification_allowed and can_increase_independent_count
are independent columns and never auto-flip here.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app.db.repo import AuditRepo

PLATFORM_TG = "telegram"

_TG_HANDLE = re.compile(r"^@?[A-Za-z0-9_]{4,64}$")
_TG_URL = re.compile(r"^(?:https?://)?t\.me/(?:s/)?@?([A-Za-z0-9_]{4,64})/?$")
_BAD_HOSTS = re.compile(
    r"^(localhost|metadata\.google\.internal|169\.254\.169\.254)$",
    re.IGNORECASE)
_POLLING_TIERS = {"VERY_HIGH": 1, "HIGH": 2, "NORMAL": 3, "LOW": 4}
_POLICY_VALUES = ("AUTO", "VERIFY_ONLY", "DISCOVERY_ONLY",
                  "NEVER_PUBLISH")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_public_http_host(host: str) -> bool:
    if not host or _BAD_HOSTS.match(host):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or not addr.is_global):
            return False
    return True


class SourceManager:
    def __init__(self, db) -> None:
        self.db = db

    # -------------------------------------------------------------- helpers
    @staticmethod
    def normalize(raw: str) -> dict[str, Any] | None:
        """URL/@username -> {platform, external_id, url} or None if invalid."""
        raw = (raw or "").strip()
        if not raw or raw.startswith(("file://", "ftp://", "gopher://")):
            return None
        m = _TG_URL.match(raw) or _TG_HANDLE.match(raw) and None
        if raw.startswith("@") and _TG_HANDLE.match(raw):
            h = raw.lstrip("@")
            return {"platform": PLATFORM_TG, "external_id": h,
                    "url": f"https://t.me/s/{h}"}
        m2 = _TG_URL.match(raw)
        if m2:
            h = m2.group(1)
            return {"platform": PLATFORM_TG, "external_id": h,
                    "url": f"https://t.me/s/{h}"}
        parsed = urlparse(raw)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        if not _is_public_http_host(parsed.hostname):
            return None
        path = (parsed.path or "").lower()
        if path.endswith((".xml", ".rss", "/feed", "/rss", "/atom")):
            platform = "rss"
        else:
            platform = "website"
        return {"platform": platform, "external_id": parsed.netloc,
                "url": raw}

    def find_endpoint(self, norm: dict[str, Any]) -> dict | None:
        return self.db.query_one(
            "SELECT * FROM sources WHERE url=? OR (platform=? AND external_id=?)",
            (norm["url"], norm["platform"], norm["external_id"]))

    def find_identity(self, ident: str) -> dict | None:
        if not ident:
            return None
        return self.db.query_one(
            "SELECT * FROM sources WHERE identity=? LIMIT 1", (ident,))

    def suggest_identity(self, norm: dict[str, Any]) -> str:
        if norm["platform"] == PLATFORM_TG:
            return norm["external_id"].replace("_", " ").title().replace(" ", "")
        host = norm["url"].split("//")[-1].split("/")[0]
        parts = host.replace("www.", "").split(".")
        return "".join(p.capitalize() for p in parts[:2]) or host

    # ------------------------------------------------------------ add / edit
    def add_source(self, raw: str, *, display_name: str = "",
                   category: str = "", language: str = "", priority: int = 50,
                   polling_tier: str = "NORMAL", identity: str = "",
                   actor: str = "system") -> dict[str, Any]:
        """Returns {ok, status, message_fa, source?} — no exceptions."""
        norm = self.normalize(raw)
        if not norm:
            return {"ok": False, "status": "REJECTED",
                    "message_fa": "❌ آدرس نامعتبر یا غیرمجاز (فقط https/Telegram عمومی)"}
        existing = self.find_endpoint(norm)
        if existing:
            return {"ok": True, "status": "EXISTS",
                    "message_fa": f"⚠️ این اندپوینت از قبل ثبت است: {existing['name']}",
                    "source": existing}
        ident = identity or self.suggest_identity(norm)
        if not self.find_identity(ident):
            ident_norm = ident  # first endpoint of this entity owns it
        name = display_name or (f"@{norm['external_id']}"
                                if norm["platform"] == PLATFORM_TG
                                else norm["external_id"])
        platform = "x" if "/x.com/" in norm["url"] or "twitter.com" in norm["url"] \
            else norm["platform"]
        status = "DISCOVERED" if platform == "x" else "APPROVED"
        # telegram endpoints poll via the t.me/s/ web preview collector
        # (this deployment has no Telethon credentials); source_type drives
        # the scheduler dispatch — "direct" would never be fetched.
        stype = ("telegram_web_preview" if platform == PLATFORM_TG
                 else ("rss" if platform == "rss" else "direct"))
        self.db.execute(
            "INSERT INTO sources (name, platform, external_id, url, language,"
            " category, source_type, status, enabled, priority,"
            " polling_interval_seconds, source_control_state, identity,"
            " created_at, notes, verification_allowed,"
            " can_increase_independent_count, publication_policy,"
            " polling_tier)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OWNER_ENABLED',"
            " ?, ?, 'added via source manager', 1, 1, ?, ?)",
            (name, platform, norm["external_id"], norm["url"],
             language or ("fa" if platform == PLATFORM_TG else ""),
             category or "general", stype, status,
             0 if status == "DISCOVERED" else 1, priority,
             self.polling_seconds(polling_tier), ident, _now(),
             "AUTO" if status != "DISCOVERED" else "NEVER_PUBLISH",
             polling_tier))
        row = self.find_endpoint(norm)
        AuditRepo(self.db).log(actor, "add_source", "sources", row["id"],
                               old="", new=f"{name} ({platform}, {ident})")
        msg = ("✅ منبع اضافه شد" if status != "DISCOVERED"
               else "⚠️ منبع اضافه شد ولی دسترسی محدود است (X بدون API پولی)")
        return {"ok": True, "status": status, "message_fa": msg,
                "source": row}

    @staticmethod
    def polling_seconds(tier: str) -> int:
        return {"VERY_HIGH": 60, "HIGH": 120, "NORMAL": 240, "LOW": 900}.get(
            tier, 240)

    def set_enabled(self, source_id: int, enabled: bool, actor: str) -> bool:
        row = self.db.query_one("SELECT * FROM sources WHERE id=?", (source_id,))
        if not row:
            return False
        self.db.execute(
            "UPDATE sources SET enabled=?, source_control_state=?, last_error=''"
            " WHERE id=?",
            (1 if enabled else 0,
             "OWNER_ENABLED" if enabled else "OWNER_DISABLED", source_id))
        AuditRepo(self.db).log(actor, "enable_source" if enabled else
                               "disable_source", "sources", source_id,
                               old=str(row["enabled"]),
                               new="1" if enabled else "0")
        return True

    def update_source(self, source_id: int, actor: str, **fields: Any) -> bool:
        row = self.db.query_one("SELECT * FROM sources WHERE id=?", (source_id,))
        if not row:
            return False
        allowed = {}
        if "identity" in fields and fields["identity"]:
            allowed["identity"] = str(fields["identity"]).strip()[:60]
        if "category" in fields and fields["category"]:
            allowed["category"] = str(fields["category"]).strip()[:40]
        if "priority" in fields:
            try:
                allowed["priority"] = max(1, min(int(fields["priority"]), 99))
            except (TypeError, ValueError):
                pass
        if "polling_tier" in fields and fields["polling_tier"] in _POLLING_TIERS:
            allowed["polling_tier"] = fields["polling_tier"]
            allowed["polling_interval_seconds"] = \
                self.polling_seconds(fields["polling_tier"])
        if "publication_policy" in fields and \
                fields["publication_policy"] in _POLICY_VALUES:
            allowed["publication_policy"] = fields["publication_policy"]
        if "status" in fields and fields["status"] in (
                "APPROVED", "DISCOVERED", "BLOCKED"):
            allowed["status"] = fields["status"]
            # archive = BLOCKED + disabled; historical rows stay intact
            if fields["status"] == "BLOCKED":
                allowed["enabled"] = 0
        if not allowed:
            return False
        sets = ", ".join(f"{k}=?" for k in allowed)
        self.db.execute(f"UPDATE sources SET {sets} WHERE id=?",
                        (*allowed.values(), source_id))
        for k, v in allowed.items():
            AuditRepo(self.db).log(actor, f"update_source.{k}", "sources",
                                   source_id, old=str(row[k]), new=str(v))
        return True

    # ------------------------------------------------------------ trust rules
    @staticmethod
    def can_publish_now(db, source_id: int) -> bool:
        """Publication-time gate: current source state ALWAYS wins — a
        source disabled after a job was queued cannot publish it."""
        row = db.query_one(
            "SELECT enabled, status, publication_policy, identity FROM sources"
            " WHERE id=?", (source_id,))
        if not row or not row["enabled"] or row["status"] == "BLOCKED":
            return False
        if row["publication_policy"] in ("VERIFY_ONLY", "DISCOVERY_ONLY",
                                         "NEVER_PUBLISH"):
            return False
        return True

    def test_source(self, source_id: int) -> dict[str, Any]:
        """Safe read-only probe (§13). Never publishes anything."""
        row = self.db.query_one("SELECT * FROM sources WHERE id=?", (source_id,))
        if not row:
            return {"ok": False, "error": "not-found"}
        norm = self.normalize(row["url"])
        if not norm:
            return {"ok": False, "error": "invalid-url"}
        import httpx
        try:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                resp = client.get(norm["url"],
                                  headers={"User-Agent": "Mozilla/5.0 (compatible; RastehBot/1.0)"})
        except Exception as ex:  # noqa: BLE001 — probe reports, never raises
            self.db.execute(
                "UPDATE sources SET last_error=?, last_check_at=? WHERE id=?",
                (str(ex)[:160], _now(), source_id))
            return {"ok": False, "error": str(ex)[:120]}
        ok = resp.status_code == 200 and len(resp.content) > 500
        latest = ""
        if ok and norm["platform"] == PLATFORM_TG:
            times = re.findall(r'<time datetime="([^"]+)"', resp.text)
            latest = times[-1] if times else ""
        self.db.execute(
            "UPDATE sources SET last_check_at=?, last_success_at=?,"
            " last_error='' WHERE id=?",
            (_now(), _now() if ok else row["last_success_at"], source_id))
        if not ok:
            self.db.execute(
                "UPDATE sources SET last_error=? WHERE id=?",
                (f"HTTP {resp.status_code}", source_id))
        return {"ok": ok, "http": resp.status_code, "bytes": len(resp.content),
                "platform": norm["platform"], "latest_item": latest,
                "reachable": True}
