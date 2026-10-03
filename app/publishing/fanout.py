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
        # PART-8 CORE-009: additional platforms join automatically when their
        # PlatformAccount is enabled AND legitimately authenticated; a
        # platform failure never blocks the others (independent adapters)
        try:
            from app.publishing import platform_accounts as _pa
            for plat in _pa.active_publish_platforms(getattr(
                    settings_repo, "db", None) or _db_from(settings_repo)):
                if plat not in ("telegram", "web", "website") and plat not in platforms:
                    platforms.append(plat)
        except Exception:  # noqa: BLE001 — platform registry must never block fanout
            pass
    return platforms


def _db_from(settings_repo):
    return getattr(settings_repo, "_db", None)
