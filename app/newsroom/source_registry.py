"""Source registry import (PART-3-C §10-12) — candidates ONLY, never auto-enabled.
Identity dedup: one organization/person = ONE canonical source identity with
multiple endpoints (website/X/Telegram are endpoints, not independent sources)."""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from app.db.repo import SourcesRepo
from app.newsroom.claim_model import normalize

# canonical identity groups: endpoints of the same org/person share identity_key
IDENTITY_GROUPS: dict[str, list[str]] = {
    "trump": ["trump x", "trump truth social", "donald trump"],
    "netanyahu": ["netanyahu x", "netanyahu telegram", "israeli pm"],
    "centcom": ["centcom en", "centcom ar", "centcom"],
    "idf": ["idf en", "idf hebrew", "idf"],
    "iran international": ["iran international en", "iran international fa",
                           "iran international"],
    "al jazeera": ["al jazeera english", "al jazeera arabic", "al jazeera"],
    "state dept": ["state department", "state dept spokesperson"],
}

ROLE_META = {
    "INDEPENDENT_NEWSROOM": {"verification_eligible": True, "tier": "B"},
    "OFFICIAL_PRIMARY": {"verification_eligible": False, "tier": "A",
                         "note": "authoritative only for 'they said X'"},
    "OSINT_DATA": {"verification_eligible": False, "tier": "A",
                   "note": "evidence layer, not duplicate newsroom"},
    "PERSON_STATEMENT": {"verification_eligible": False, "tier": "A",
                         "note": "statement evidence only"},
    "ANALYSIS": {"verification_eligible": False, "tier": "C",
                 "note": "opinion/analysis — never factual corroboration"},
}


def identity_key(name: str) -> str:
    n = normalize(name or "").lower()
    for key, aliases in IDENTITY_GROUPS.items():
        if any(a in n for a in aliases):
            return key
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def parse_csv(content: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content))
    return [dict(row) for row in reader if any(v.strip() for v in row.values() if v)]


def import_registry(db, csv_content: str) -> dict[str, int]:
    """Import as CANDIDATE rows (owner_enabled=false). Endpoint rows of the same
    identity collapse into ONE source identity (extra endpoints in notes)."""
    repo = SourcesRepo(db)
    existing = {r["name"].strip().lower(): r["id"] for r in repo.list()}
    by_identity: dict[str, int] = {}
    imported = identities = 0
    for row in parse_csv(csv_content):
        name = (row.get("name") or row.get("Name") or "").strip()
        if not name:
            continue
        if name.lower() in existing:  # already imported (rerun idempotency)
            by_identity[identity_key(name)] = existing[name.lower()]
            continue
        role = (row.get("role") or "INDEPENDENT_NEWSROOM").strip().upper()
        if role not in ROLE_META:
            role = "INDEPENDENT_NEWSROOM"
        platform = (row.get("platform") or "rss").strip().lower()
        platform = {"x": "x", "twitter": "x", "telegram": "telegram", "rss": "rss",
                    "website": "website", "web": "website"}.get(platform, "rss")
        key = identity_key(name)
        if key in by_identity:
            sid = by_identity[key]
            cur = repo.get(sid)
            repo.update(sid, notes=(cur["notes"] + f" | endpoint:{platform}:{name}")[:500])
            imported += 1
            continue
        meta = ROLE_META[role]
        sid = repo.create(
            name=name, platform=platform, url=row.get("url", ""),
            language=(row.get("language") or "en"), status="DISCOVERED",
            source_type="official_institution" if role == "OFFICIAL_PRIMARY" else "news_organization",
            source_role="OFFICIAL_PRIMARY" if role == "OFFICIAL_PRIMARY" else "MAJOR_NEWSROOM",
            verification_allowed=False,          # owner approves later (§10)
            priority=90 if meta["tier"] == "A" else 95,
            polling_interval_min=120,
            notes=f"CANDIDATE tier={meta['tier']} role={role} "
                  f"note={meta.get('note', '')} | {row.get('notes', '')}"[:500])
        repo.update(sid, enabled=0, source_control_state="DISCOVERY_ONLY")
        by_identity[key] = sid
        imported += 1
        identities += 1
    return {"imported": imported, "unique_identities": identities}
