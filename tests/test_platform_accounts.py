"""PART-8 — CORE-009 PlatformAccount registry + fanout independence."""
from app.db.repo import SettingsRepo
from app.publishing import platform_accounts as pa
from app.publishing.fanout import distribution_plan


class S:
    telegram_publish_ready = True
    public_base_url = ""


def test_defaults_seeded_idempotent(db):
    pa.ensure_defaults(db)
    pa.ensure_defaults(db)
    rows = pa.accounts(db)
    assert {r["platform"] for r in rows} == set(pa.PLATFORMS)
    by_name = {r["platform"]: r for r in rows}
    assert by_name["x"]["auth_state"] == "BLOCKED_EXTERNAL"
    assert by_name["instagram"]["auth_state"] == "AUTH_REQUIRED"


def test_fanout_only_includes_authenticated(db):
    repo = SettingsRepo(db)
    pa.ensure_defaults(db)
    plan = distribution_plan("CONFIRMED", S(), repo)
    assert "telegram" in plan
    assert not any(p in plan for p in ("x", "instagram", "threads", "facebook"))
    # enabling a configured platform adds it; a BLOCKED one never joins
    pa.set_state(db, "x", enabled=True, auth_state="BLOCKED_EXTERNAL")
    pa.set_state(db, "telegram", enabled=True, auth_state="CONFIGURED")
    plan2 = distribution_plan("CONFIRMED", S(), repo)
    assert "x" not in plan2
    pa.set_state(db, "x", auth_state="CONFIGURED")
    plan3 = distribution_plan("CONFIRMED", S(), repo)
    assert "x" in plan3


def test_platform_failure_isolation(db):
    pa.ensure_defaults(db)
    pa.mark_error(db, "x", "api down")
    pa.mark_published(db, "telegram")
    assert pa.get(db, "x")["health"] == "ERROR"
    assert pa.get(db, "telegram")["health"] == "HEALTHY"
    assert pa.get(db, "telegram")["last_publish_at"]
