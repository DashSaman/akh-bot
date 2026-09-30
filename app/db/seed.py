"""Clean-install source seeding: load config/source-seed.example.yml ONLY when the
sources table is empty. Existing/migrated registries are never touched.

Identity discovery: at first activation the current remote identity is resolved
(handle → canonical URL); runtime records update without losing logical identity.
"""
from __future__ import annotations

import logging
import os

import yaml

log = logging.getLogger("akh.seed")


def seed_sources_if_empty(db, seed_path: str | None = None) -> int:
    from app.db.repo import SourcesRepo

    repo = SourcesRepo(db)
    if repo.list():
        return 0  # migrated/existing registry wins — never reseed
    path = seed_path or os.path.join("config", "source-seed.example.yml")
    if not os.path.exists(path):
        log.info("no seed file at %s — clean DB starts empty", path)
        return 0
    data = yaml.safe_load(open(path, encoding="utf-8")) or {}
    n = 0
    for s in data.get("sources", []):
        repo.create(
            name=s.get("name", ""),
            platform=s.get("platform", "rss"),
            url=s.get("url", "") or "",
            external_id=s.get("handle", ""),
            language=s.get("language", "und"),
            status="APPROVED" if s.get("enabled") else "DISCOVERED",
            source_type="telegram_web_preview" if s.get("platform") == "telegram" else "news_organization",
            source_role=s.get("source_role", "MAJOR_NEWSROOM"),
            verification_allowed=bool(s.get("verification_allowed")),
            can_increase_independent_count=bool(s.get("verification_allowed"))
            and s.get("source_role") != "AGGREGATOR",
            polling_interval_min=1 if int(s.get("detection_priority", 60)) >= 95 else 5,
            notes=(s.get("notes", "") + f" | display:{s.get('public_display_name','')}"
                   f" | prio:{s.get('detection_priority', 60)}"
                   f" | translate:{bool(s.get('translation_required'))}"),
        )
        n += 1
    log.info("seeded %s sources from %s (clean install)", n, path)
    return n
