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


# --------------------------------------------------------------------------
# MASTER-FINAL: full XLSX registry import (one sources ROW PER ENDPOINT,
# canonical `identity` = authoritative Entity ID). Endpoints of one identity
# never inflate independent-origin counts (§4); per-endpoint activation is
# truthful (§17). Idempotent by (identity, platform, url).
# --------------------------------------------------------------------------

PLATFORM_MAP = {"website": "website", "web": "website", "rss": "rss",
                "telegram": "telegram", "x": "x", "twitter": "x",
                "truth social": "x", "threads": "x"}

SPEED_TIERS = {  # XLSX speed metadata → tier + polling seconds (§8)
    # keyed by the MAX minute bound found in the speed text
    2: ("FAST", 120), 5: ("MID", 240), 15: ("SLOW", 600),
}


def speed_tier_of(speed_text: str) -> tuple[str, int]:
    """Map XLSX speed strings ('1–2 min', '5–15 min', 'event-driven') to a
    tier + polling interval using the range's upper bound; event-driven and
    long-form tiers poll slowly. Polite defaults otherwise."""
    t = (speed_text or "").lower()
    if not t:
        return ("MID", 300)
    if "real" in t:
        return ("FAST", 120)
    if "event" in t or "daily" in t or "document" in t:
        return ("EVENT", 1800)
    nums = [int(n) for n in re.findall(r"\d+", t)]
    bound = max(nums) if nums else 5
    for limit, val in sorted(SPEED_TIERS.items()):
        if bound <= limit:
            return val
    return ("SLOW", 900)


def role_of(trust_use: str, independent: str, kind: str) -> tuple[str, bool, bool]:
    """(source_role, verification_allowed, can_increase_independent_count)
    from XLSX semantics (§6). Priority is speed — NEVER truth."""
    tu = (trust_use or "").lower()
    ind = (independent or "").lower()
    kind_l = (kind or "").lower()
    if "official" in tu or "institution" in kind_l or "government" in kind_l:
        return "OFFICIAL_PRIMARY", False, False
    if "person" in tu or "direct person" in tu or "reporter" in kind_l \
            or "figure" in tu:
        return "PERSON_STATEMENT", False, False
    if "osint" in tu or "osint" in kind_l or "specialist" in tu or "data" in kind_l:
        # independent OSINT datasets may corroborate (EvidenceLinks, same
        # event — §24) but never as duplicate stories
        can = not ind.startswith("no")
        return "OSINT_DATA", False, can
    if "analysis" in tu:
        return "ANALYSIS", False, False
    # newsroom: independent unless a mirror of another entity's identity
    mirror = ind.startswith("no") and "same" in ind
    return "INDEPENDENT_NEWSROOM", (not mirror), (not mirror)


def _tg_handle(url: str) -> str:
    """t.me/<handle> → handle ('' for non-channel links like s/ pages)."""
    m = re.search(r"t\.me/(?:s/)?([A-Za-z0-9_]{3,64})", url or "")
    handle = m.group(1) if m else ""
    return "" if handle.lower() in ("s", "joinchat", "c") else handle


def import_full_registry(db, endpoints: list[dict]) -> dict[str, int]:
    """Import canonical endpoint rows (see scripts/import_source_xlsx.py for
    the XLSX→canonical conversion). Idempotent; never auto-modifies existing
    naya/yashar rows; APPROVED+OWNER_ENABLED so the allowlist polls them."""
    repo = SourcesRepo(db)
    stats = {"endpoints": 0, "identities": set(), "updated": 0,
             "created": 0, "blocked": 0}
    for ep in endpoints:
        identity = (ep.get("entity") or "").strip()
        platform = PLATFORM_MAP.get((ep.get("platform") or "").strip().lower(), "website")
        url = (ep.get("url") or "").strip()
        if not identity or not url:
            continue
        role, va, ciic = role_of(ep.get("trust_use") or "",
                                 ep.get("independent") or "",
                                 ep.get("kind") or "")
        # DB enum is coarse; precise XLSX semantics live in role_detail and
        # drive the behavioral columns (verification_allowed / can_increase)
        db_role = {"INDEPENDENT_NEWSROOM": "MAJOR_NEWSROOM",
                   "OFFICIAL_PRIMARY": "OFFICIAL_PRIMARY",
                   "PERSON_STATEMENT": "JOURNALIST",
                   "OSINT_DATA": "AGGREGATOR",
                   "ANALYSIS": "AGGREGATOR"}[role]
        tier, interval = speed_tier_of(ep.get("speed") or "")
        # truthful endpoint activation (§17)
        if platform in ("x",):  # X / Truth Social: no legitimate free API
            endpoint_state = "BLOCKED_AUTH"
        elif platform == "website":  # no generic collector; RSS discovered separately
            endpoint_state = "UNSUPPORTED"
        else:
            endpoint_state = "ACTIVE"
        lang = (ep.get("language") or "en").strip().lower()[:3]
        name = (ep.get("name") or identity).strip()[:120]
        source_type = ("telegram_web_preview" if platform == "telegram"
                       else ("truthsocial_endpoint" if "truth" in (ep.get("platform") or "").lower()
                             else ("rss_feed" if platform == "rss" else "website_endpoint")))
        external_id = _tg_handle(url) if platform == "telegram" else ""
        # idempotency: same identity+platform+url
        existing = db.query_one(
            "SELECT id FROM sources WHERE identity=? AND platform=? AND url=?",
            (identity, platform, url))
        if existing:
            repo.update(int(existing["id"]),
                        source_role=db_role, role_detail=role,
                        verification_allowed=va,
                        can_increase_independent_count=ciic,
                        polling_interval_seconds=interval, endpoint_state=endpoint_state,
                        speed_tier=tier, focus=(ep.get("focus") or "")[:300])
            stats["updated"] += 1
            stats["identities"].add(identity.lower())
            continue
        sid = repo.create(
            name=name, platform=platform, url=url, external_id=external_id,
            language=lang, status="APPROVED",
            source_type=source_type, source_role=db_role,
            verification_allowed=va, can_increase_independent_count=ciic,
            priority=50, polling_interval_min=max(1, interval // 60),
            notes=(f"entity={identity} | {(ep.get('trust_use') or '')[:80]}"
                   f" | evidence={url}"[:500]))
        repo.update(sid, identity=identity, endpoint_state=endpoint_state,
                    speed_tier=tier, role_detail=role,
                    focus=(ep.get("focus") or "")[:300],
                    source_control_state="OWNER_ENABLED",
                    polling_interval_seconds=interval)
        stats["created"] += 1
        stats["identities"].add(identity.lower())
        stats["endpoints"] += 1
        if endpoint_state != "ACTIVE":
            stats["blocked"] += 1
    stats["identities"] = len(stats["identities"])
    return stats
