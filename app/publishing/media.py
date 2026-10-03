"""Temporary media cache + branded fallback card + cleanup worker.

Cache lives ONLY under DATA_DIR/media-cache. Bytes are deleted once every
required publication is SENT; metadata (hash/rights/source ref) stays in DB.
"""
from __future__ import annotations

import httpx

import hashlib
import logging
import os
import time
from typing import Any

log = logging.getLogger("akh.media")

RIGHTS_DEFAULT = "UNKNOWN"  # safe default: no blind republication


def cache_dir() -> str:
    d = os.path.join(os.environ.get("DATA_DIR", "/data"), "media-cache")
    os.makedirs(d, exist_ok=True)
    return d


def save_temp(blob: bytes, ext: str, story_id: int) -> dict[str, Any]:
    h = hashlib.sha256(blob).hexdigest()
    path = os.path.join(cache_dir(), f"{story_id}-{h[:12]}.{ext}")
    with open(path, "wb") as f:
        f.write(blob)
    return {"path": path, "sha": h, "size_bytes": len(blob),
            "rights_policy": RIGHTS_DEFAULT, "download_status": "CACHED"}


def record(db, story_id: int, meta: dict[str, Any]) -> None:
    import json

    db.execute(
        "INSERT OR REPLACE INTO media_cache(path, story_id, sha, size_mb, created_at)"
        " VALUES(?,?,?,?,datetime('now'))",
        (meta["path"], story_id, meta["sha"], round(meta["size_bytes"] / 1e6, 2)))
    db.execute("UPDATE stories SET draft_json=json_set(draft_json, '$.media', ?)"
               " WHERE id=?", (json.dumps(meta, ensure_ascii=False), story_id))


def cleanup_published_and_expired(db, ttl_minutes: int = 60, max_mb: float = 512.0) -> dict[str, int]:
    """Delete local bytes for SENT stories; drop TTL-expired/partial files; enforce size cap."""
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
    return {"removed": removed}


def disk_percent() -> int:
    import shutil

    total, used, _ = shutil.disk_usage(os.environ.get("DATA_DIR", "/data") if os.name != "nt" else "C:\\")
    return int(100 * used / max(1, total))


def media_downloads_allowed(db, critical: int = 85) -> bool:
    """Disk guard: at critical level text newsroom continues, media downloads stop."""
    return disk_percent() < critical


def branded_card(headline: str, icon: str = "🟢", out_path: str = "") -> str:
    """Original Pillow news card (no fake photo): icon + Persian headline + brand."""
    from PIL import Image, ImageDraw

    W, H = 1200, 675
    img = Image.new("RGB", (W, H), (15, 20, 25))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 12], fill=(63, 185, 80))
    d.text((60, 80), icon, fill=(63, 185, 80))
    # Persian renders right-to-left; draw wrapped headline lines
    y = 220
    line = ""
    for word in headline.split():
        trial = (word + " " + line).strip()
        if len(trial) > 38:
            d.text((W - 60, y), line, fill=(230, 237, 243), anchor="ra")
            y += 72
            line = word
        else:
            line = trial
    if line:
        d.text((W - 60, y), line, fill=(230, 237, 243), anchor="ra")
    d.text((W - 60, H - 90), "راسته؟ | خبر و راستی‌آزمایی", fill=(154, 167, 179), anchor="ra")
    d.text((W - 60, H - 50), "@RastehNews", fill=(88, 166, 255), anchor="ra")
    out = out_path or os.path.join(cache_dir(), f"card-{int(time.time())}.png")
    img.save(out, "PNG")
    return out


# --------------------------------------------------------------------------
# PART-6: canonical MediaAsset (CORE-006 / MEDIA-003 / REG-025)
# TRUTHFUL labels only: ORIGINAL_MEDIA (bytes we hold), SOURCE_REFERENCE
# (metadata only — original stays at the source), BRANDED_FALLBACK (our own
# card, never presented as source media), UNAVAILABLE.
# --------------------------------------------------------------------------

MEDIA_STATUSES = ("ORIGINAL_MEDIA", "SOURCE_REFERENCE", "BRANDED_FALLBACK",
                  "UNAVAILABLE")

_STATUS_RANK = {"ORIGINAL_MEDIA": 0, "BRANDED_FALLBACK": 1,
                "SOURCE_REFERENCE": 2, "UNAVAILABLE": 3}


def register_asset(db, *, story_id: int | None, event_id: int | None,
                   raw_item_id: int | None, source_id: int, kind: str,
                   status: str, sha256: str, path: str = "",
                   remote_url: str = "", size_mb: float = 0.0,
                   caption_ref: str = "") -> int | None:
    """Idempotent canonical asset insert (checksum dedup: UNIQUE sha256)."""
    if status not in MEDIA_STATUSES or not sha256:
        return None
    db.execute(
        "INSERT OR IGNORE INTO media_assets(story_id, event_id, raw_item_id,"
        " source_id, kind, status, sha256, path, remote_url, size_mb,"
        " caption_ref, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
        (story_id, event_id, raw_item_id, source_id, kind, status, sha256,
         path, remote_url, size_mb, caption_ref))
    row = db.query_one("SELECT id FROM media_assets WHERE sha256=?", (sha256,))
    return int(row["id"]) if row else None


async def capture_original(db, *, url: str, story_id: int | None,
                           event_id: int | None, raw_item_id: int | None,
                           source_id: int, max_mb: float = 10.0,
                           client_factory=None) -> dict:
    """Capture original photo/video bytes when ACCESSIBLE, PERMITTED and
    within size limits. Result is always truthful:
      ORIGINAL_MEDIA  — bytes stored on disk under the cache dir
      SOURCE_REFERENCE — download not possible; metadata kept (no fake)
      UNAVAILABLE     — endpoint explicitly missing the media
    """
    import hashlib as _h

    if not url:
        return {"status": "UNAVAILABLE", "sha": "", "path": ""}
    if not media_downloads_allowed(db):
        return {"status": "SOURCE_REFERENCE", "sha": _sha_ref(url), "path": "",
                "reason": "disk_guard"}
    try:
        factory = client_factory or httpx.AsyncClient
        async with factory(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
        if resp.status_code != 200 or not resp.content:
            return {"status": "SOURCE_REFERENCE", "sha": _sha_ref(url), "path": "",
                    "reason": f"HTTP {resp.status_code}"}
        size_mb = len(resp.content) / 1_048_576
        if size_mb > max_mb:
            return {"status": "SOURCE_REFERENCE", "sha": _sha_ref(url), "path": "",
                    "reason": "size_limit"}
        ctype = (resp.headers.get("content-type") or "").lower()
        kind = "video" if "video" in ctype else "photo"
        sha = _h.sha256(resp.content).hexdigest()
        meta = save_temp(resp.content, ".mp4" if kind == "video" else ".jpg",
                         story_id or 0)
        aid = register_asset(db, story_id=story_id, event_id=event_id,
                             raw_item_id=raw_item_id, source_id=source_id,
                             kind=kind, status="ORIGINAL_MEDIA", sha256=sha,
                             path=meta["path"], remote_url=url, size_mb=size_mb)
        record(db, story_id or 0, dict(meta, size_mb=round(size_mb, 2)))
        return {"status": "ORIGINAL_MEDIA", "sha": sha, "path": meta["path"],
                "asset_id": aid, "kind": kind}
    except Exception as ex:  # noqa: BLE001 — never break publishing on media
        return {"status": "SOURCE_REFERENCE", "sha": _sha_ref(url), "path": "",
                "reason": f"capture: {str(ex)[:60]}"}


def _sha_ref(url: str) -> str:
    import hashlib as _h

    return "ref-" + _h.sha256((url or "").encode()).hexdigest()[:40]


def register_source_reference(db, *, url: str, story_id: int | None,
                              event_id: int | None, raw_item_id: int | None,
                              source_id: int, kind: str = "photo",
                              caption_ref: str = "") -> int | None:
    """SOURCE_REFERENCE: the original media stays at the source; we keep the
    metadata link only (typical for WEB_FALLBACK without Telethon bytes)."""
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
    """Our own branded card — explicitly BRANDED_FALLBACK, never presented as
    source media (REG-025). Renders via cards.render_card_v2 (proper Persian
    shaping); any renderer failure → NO card (text-only), never a broken image."""
    import hashlib as _h

    from app.publishing.cards import render_card_v2
    if not lifecycle:
        lifecycle = {"🔴": "PROVISIONAL", "🟠": "CONFLICTING"}.get(icon, "VERIFIED")
    try:
        card = render_card_v2(headline, lifecycle=lifecycle)
    except Exception:  # noqa: BLE001 — broken card must never reach the channel
        return None
    sha = _h.sha256(open(card, "rb").read()).hexdigest() if card else ""
    return register_asset(db, story_id=story_id, event_id=event_id,
                          raw_item_id=None, source_id=0, kind="card",
                          status="BRANDED_FALLBACK", sha256=sha or _sha_ref(headline),
                          path=card or "")


def best_for_story(db, story_id: int) -> dict | None:
    """Best publishable asset: ORIGINAL bytes first, then branded card.
    SOURCE_REFERENCE alone is never 'best' — we cannot publish a link as an
    original photo truthfully."""
    rows = db.query(
        "SELECT * FROM media_assets WHERE story_id=?"
        " AND status IN ('ORIGINAL_MEDIA','BRANDED_FALLBACK')", (story_id,))
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: (_STATUS_RANK[r["status"]], -r["id"]))
    return dict(rows[0])


def assets_for_story(db, story_id: int) -> list[dict]:
    """Full truthful inventory (admin/verification view)."""
    return [dict(r) for r in db.query(
        "SELECT * FROM media_assets WHERE story_id=? ORDER BY id", (story_id,))]
