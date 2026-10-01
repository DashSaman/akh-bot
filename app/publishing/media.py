"""Temporary media cache + branded fallback card + cleanup worker.

Cache lives ONLY under DATA_DIR/media-cache. Bytes are deleted once every
required publication is SENT; metadata (hash/rights/source ref) stays in DB.
"""
from __future__ import annotations

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
