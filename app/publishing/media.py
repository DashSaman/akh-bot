"""Original-media pipeline (FINAL MEDIA policy, 2026-10-04 closeout).

NO permanent binary storage for source media:
  - SOURCE_REFERENCE rows keep metadata only (url/hash/rights/telegram file_id)
  - bytes, when unavoidable, live in a bounded TEMP dir and are deleted
    immediately after the Telegram upload (success OR failure).
  - the old persistent media-cache is legacy; cleanup sweeps it.
Generated branded cards are RETIRED from production (BRANDED_FALLBACK_ENABLED
=false); renderer code stays only for tests/history.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any

import httpx

log = logging.getLogger("akh.media")

RIGHTS_DEFAULT = "UNKNOWN"  # safe default: no blind republication

TEMP_MEDIA_DIR = "/tmp/akhmedia"          # ephemeral, never the data volume
TEMP_MAX_BYTES = 20 * 1024 * 1024         # per-file cap for temp downloads
TEMP_DIR_MAX_BYTES = 200 * 1024 * 1024    # hard ceiling for the temp dir


def cache_dir() -> str:
    """LEGACY persistent dir — kept only so the cleanup worker can drain it."""
    d = os.path.join(os.environ.get("DATA_DIR", "/data"), "media-cache")
    os.makedirs(d, exist_ok=True)
    return d


def temp_dir() -> str:
    os.makedirs(TEMP_MEDIA_DIR, exist_ok=True)
    return TEMP_MEDIA_DIR


def save_temp(blob: bytes, ext: str, story_id: int) -> dict[str, Any]:
    """Write media bytes to the bounded TEMP dir (auto-cleaned after send)."""
    enforce_temp_budget(len(blob))
    h = hashlib.sha256(blob).hexdigest()
    path = os.path.join(temp_dir(), f"{story_id}-{h[:12]}{ext}")
    with open(path, "wb") as f:
        f.write(blob)
    return {"path": path, "sha": h, "size_bytes": len(blob),
            "rights_policy": RIGHTS_DEFAULT, "download_status": "TEMP"}


def enforce_temp_budget(incoming: int = 0) -> None:
    """Disk guard: temp media must stay bounded (oldest files evicted first)."""
    now = time.time()
    files = []
    total = 0
    try:
        entries = os.listdir(temp_dir())
    except OSError:
        return
    for fn in entries:
        p = os.path.join(temp_dir(), fn)
        try:
            if now - os.path.getmtime(p) > 1800:  # abandoned temp > 30min
                os.unlink(p)
                continue
            sz = os.path.getsize(p)
            total += sz
            files.append((os.path.getmtime(p), p, sz))
        except OSError:
            continue
    for _, p, sz in sorted(files):
        if total + incoming <= TEMP_DIR_MAX_BYTES:
            break
        try:
            os.unlink(p)
            total -= sz
        except OSError:
            pass


def record(db, story_id: int, meta: dict[str, Any]) -> None:
    import json

    db.execute(
        "INSERT OR REPLACE INTO media_cache(path, story_id, sha, size_mb, created_at)"
        " VALUES(?,?,?,?,datetime('now'))",
        (meta["path"], story_id, meta["sha"], round(meta["size_bytes"] / 1e6, 2)))
    db.execute("UPDATE stories SET draft_json=json_set(draft_json, '$.media', ?)"
               " WHERE id=?", (json.dumps(meta, ensure_ascii=False), story_id))


def cleanup_published_and_expired(db, ttl_minutes: int = 60, max_mb: float = 512.0) -> dict[str, int]:
    """LEGACY persistent-cache drain + temp sweep. Bytes die; metadata stays."""
    freed = removed = 0
    now = time.time()
    for row in db.query(
            "SELECT m.path FROM media_cache m WHERE"
            " (SELECT COUNT(*) FROM publications p WHERE p.story_id=m.story_id"
            "  AND p.status='SENT') > 0"
            " OR m.created_at <= datetime('now', ?)", (f"-{ttl_minutes} minutes",)):
        try:
            os.unlink(row["path"])
            removed += 1
        except OSError:
            pass
        db.execute("DELETE FROM media_cache WHERE path=?", (row["path"],))
    # partial/temp garbage (any non-recorded file older than ttl)
    for fn in os.listdir(cache_dir()):
        p = os.path.join(cache_dir(), fn)
        try:
            if now - os.path.getmtime(p) > ttl_minutes * 60 and not db.query_one(
                    "SELECT 1 FROM media_cache WHERE path=?", (p,)):
                os.unlink(p)
                removed += 1
        except OSError:
            pass
    # size cap: oldest first
    total = 0
    files = []
    for fn in os.listdir(cache_dir()):
        p = os.path.join(cache_dir(), fn)
        try:
            sz = os.path.getsize(p)
            total += sz
            files.append((os.path.getmtime(p), p, sz))
        except OSError:
            continue
    for _, p, sz in sorted(files):
        if total <= max_mb * 1e6:
            break
        try:
            os.unlink(p)
            total -= sz
            removed += 1
            db.execute("DELETE FROM media_cache WHERE path=?", (p,))
        except OSError:
            pass
    enforce_temp_budget()
    return {"removed": removed}


def disk_percent() -> int:
    import shutil

    path = os.environ.get("DATA_DIR", "/data") if os.name != "nt" else "C:\\"
    if not os.path.isdir(path):
        path = os.getcwd()  # CI/clean-checkout: /data absent — measure cwd
    total, used, _ = shutil.disk_usage(path)
    return int(100 * used / max(1, total))


def media_downloads_allowed(db, critical: int = 85) -> bool:
    """Disk guard: at critical level text newsroom continues, media downloads stop."""
    return disk_percent() < critical


# --------------------------------------------------------------------------
# PART-6: canonical MediaAsset (CORE-006 / MEDIA-003 / REG-025)
# TRUTHFUL labels only: ORIGINAL_MEDIA (bytes we hold), SOURCE_REFERENCE
# (metadata only — original stays at the source), BRANDED_FALLBACK (RETIRED
# from production; kept for tests/history only), UNAVAILABLE.
# --------------------------------------------------------------------------

MEDIA_STATUSES = ("ORIGINAL_MEDIA", "SOURCE_REFERENCE", "BRANDED_FALLBACK",
                  "UNAVAILABLE")

_STATUS_RANK = {"ORIGINAL_MEDIA": 0, "SOURCE_REFERENCE": 1,
                "BRANDED_FALLBACK": 2, "UNAVAILABLE": 3}


def register_asset(db, *, story_id: int | None, event_id: int | None,
                   raw_item_id: int | None, source_id: int, kind: str,
                   status: str, sha256: str, path: str = "",
                   remote_url: str = "", size_mb: float = 0.0,
                   caption_ref: str = "",
                   telegram_file_id: str = "",
                   meta_json: str = "") -> int | None:
    """Idempotent canonical asset insert (checksum dedup: UNIQUE sha256)."""
    if status not in MEDIA_STATUSES or not sha256:
        return None
    db.execute(
        "INSERT OR IGNORE INTO media_assets(story_id, event_id, raw_item_id,"
        " source_id, kind, status, sha256, path, remote_url, size_mb,"
        " caption_ref, telegram_file_id, meta_json, created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
        (story_id, event_id, raw_item_id, source_id, kind, status, sha256,
         path, remote_url, size_mb, caption_ref, telegram_file_id, meta_json))
    row = db.query_one("SELECT id FROM media_assets WHERE sha256=?", (sha256,))
    return int(row["id"]) if row else None


def set_telegram_file_id(db, asset_id: int, file_id: str) -> None:
    if asset_id and file_id:
        db.execute("UPDATE media_assets SET telegram_file_id=? WHERE id=?",
                   (file_id, asset_id))


async def download_to_temp(url: str, story_id: int, *, max_bytes: int = TEMP_MAX_BYTES,
                           client_factory=None) -> str:
    """Bounded temp download (LAST resort when Telegram can't fetch the URL
    itself). The caller MUST delete the file after the upload attempt —
    send_media_ref does this in a finally block; the budget sweeper is the
    safety net for crashes."""
    import tempfile as _tf

    try:
        factory = client_factory or httpx.AsyncClient
        async with factory(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return ""
        blob = resp.content
        if len(blob) > max_bytes:
            return ""
        enforce_temp_budget(len(blob))
        h = hashlib.sha256(blob).hexdigest()[:12]
        path = os.path.join(temp_dir(), f"{story_id}-{h}")
        with open(path, "wb") as f:
            f.write(blob)
        return path
    except Exception:  # noqa: BLE001
        return ""


def _sha_ref(url: str) -> str:
    import hashlib as _h

    return "ref-" + _h.sha256((url or "").encode()).hexdigest()[:40]


def register_source_reference(db, *, url: str, story_id: int | None,
                              event_id: int | None, raw_item_id: int | None,
                              source_id: int, kind: str = "photo",
                              caption_ref: str = "") -> int | None:
    """SOURCE_REFERENCE: the original media stays at the source; we keep the
    metadata link only. Publishable via URL-direct (Telegram fetches the
    original) — never via a generated fake image."""
    if not url:
        return None
    return register_asset(db, story_id=story_id, event_id=event_id,
                          raw_item_id=raw_item_id, source_id=source_id,
                          kind=kind, status="SOURCE_REFERENCE",
                          sha256=_sha_ref(url), remote_url=url,
                          caption_ref=caption_ref)


def register_branded_fallback(db, *, story_id: int, event_id: int | None,
                              headline: str, icon: str = "🟢",
                              lifecycle: str = "") -> int | None:
    """RETIRED (FINAL MEDIA policy): branded headline-cards must never reach
    the channel — the owner regression showed redundant/mismatched text.
    Kept only so historical tests/rows stay explainable; always returns None
    unless explicitly re-enabled for renderer tests."""
    from app.config import get_settings
    if not getattr(get_settings(), "media_fallback_cards_enabled", False):
        return None
    import hashlib as _h

    from app.publishing.cards import render_card_v2
    if not lifecycle:
        lifecycle = {"🔴": "PROVISIONAL", "🟠": "CONFLICTING"}.get(icon, "VERIFIED")
    try:
        card = render_card_v2(headline, lifecycle=lifecycle, out_path=os.path.join(temp_dir(), f"card-{int(time.time())}.png"))
    except Exception:  # noqa: BLE001
        return None
    sha = _h.sha256(open(card, "rb").read()).hexdigest() if card else ""
    return register_asset(db, story_id=story_id, event_id=event_id,
                          raw_item_id=None, source_id=0, kind="card",
                          status="BRANDED_FALLBACK", sha256=sha or _sha_ref(headline),
                          path=card or "")


UA = "Mozilla/5.0 (compatible; RastehBot/1.0)"


async def fetch_og_media(url: str, client_factory=None) -> list[dict[str, str]]:
    """Resolve og:image / og:video / twitter:image from the ORIGINAL article
    page (async). Bounded: 8s timeout, HTML only."""
    if not url:
        return []
    try:
        factory = client_factory or httpx.AsyncClient
        async with factory(timeout=8, follow_redirects=True,
                           headers={"User-Agent": UA}) as client:
            resp = await client.get(url)
        return _parse_og(resp)
    except Exception:  # noqa: BLE001
        return []


def fetch_og_media_sync(url: str) -> list[dict[str, str]]:
    """Sync variant for the (sync) pipeline attach step."""
    if not url:
        return []
    try:
        with httpx.Client(timeout=8, follow_redirects=True,
                          headers={"User-Agent": UA}) as client:
            resp = client.get(url)
        return _parse_og(resp)
    except Exception:  # noqa: BLE001
        return []


def _parse_og(resp) -> list[dict[str, str]]:
    import re as _re

    if resp.status_code != 200 or "html" not in (resp.headers.get("content-type") or "html").lower():
        return []
    head = resp.text[:60000]
    props = dict(_re.findall(
        r'<meta[^>]+(?:property|name)=["\'](og:(?:image|video)(?::secure_url)?|twitter:(?:image|image:src))["\'][^>]+content=["\']([^"\']+)["\']',
        head, _re.I))
    flipped = dict(_re.findall(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](og:(?:image|video)(?::secure_url)?|twitter:(?:image|image:src))["\']',
        head, _re.I))
    for k, v in flipped.items():
        props.setdefault(k, v)
    refs = []
    for key in ("og:image", "og:image:secure_url", "twitter:image", "twitter:image:src"):
        v = props.get(key, "")
        if v.startswith("http"):
            refs.append({"url": v, "type": "photo"})
            break
    for key in ("og:video", "og:video:secure_url"):
        v = props.get(key, "")
        if v.startswith("http"):
            refs.append({"url": v, "type": "video"})
            break
    return refs[:2]


def best_for_story(db, story_id: int) -> dict | None:
    """Best PUBLISHABLE original asset: ORIGINAL bytes/Telegram file first,
    then SOURCE_REFERENCE with a public URL (sent URL-direct). Photo is
    preferred over video (FINAL MEDIA priority A/B). BRANDED_FALLBACK is
    NEVER returned — generated cards are retired."""
    rows = db.query(
        "SELECT * FROM media_assets WHERE story_id=?"
        " AND status IN ('ORIGINAL_MEDIA','SOURCE_REFERENCE')"
        " AND (telegram_file_id != '' OR remote_url != '')", (story_id,))
    if not rows:
        return None

    def _key(r):
        return (
            _STATUS_RANK[r["status"]],
            0 if (r["telegram_file_id"] or "") else 1,
            1 if r["kind"] == "video" else 0,  # photo before video
            -int(r["id"]),
        )

    return dict(sorted(rows, key=_key)[0])


def assets_for_story(db, story_id: int) -> list[dict]:
    """Full truthful inventory (admin/verification view)."""
    return [dict(r) for r in db.query(
        "SELECT * FROM media_assets WHERE story_id=? ORDER BY id", (story_id,))]
