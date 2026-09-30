"""Confirmed stories fan out to all ENABLED platforms; provisional stays Telegram-only."""
from __future__ import annotations


def distribution_plan(lifecycle: str, settings, settings_repo) -> list[str]:
    """PROVISIONAL/UNVERIFIED → Telegram only (fast channel).
    CONFIRMED → every configured public platform + website preview."""
    platforms: list[str] = []
    if getattr(settings, "telegram_publish_ready", False) and not settings_repo.is_paused("telegram"):
        platforms.append("telegram")
    if lifecycle.upper() in ("CONFIRMED", "CONFIRMED_OFFICIAL"):
        if getattr(settings, "public_base_url", ""):
            platforms.append("website")
        else:
            platforms.append("website_preview")
        # X / Instagram / Threads / Facebook join here when connected
    return platforms
