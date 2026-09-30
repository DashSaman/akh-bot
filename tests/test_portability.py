"""Clean-install seeding + migration invariants (watermark/priority/ledger)."""
import json

from app.db.seed import seed_sources_if_empty
from app.db.repo import SourcesRepo


def test_clean_db_seeds_baseline_catalog(db, tmp_path):
    n = seed_sources_if_empty(db, "config/source-seed.example.yml")
    assert n >= 7  # owner-requested baseline present
    names = {s["name"] for s in SourcesRepo(db).list()}
    assert any("caronline_original" in s for s in names)
    assert any("naya_foriraq" in s for s in names)
    # Tier-1 watch sources must not be verification-trusted by seed
    naya = next(s for s in SourcesRepo(db).list() if "naya" in s["name"])
    assert naya["verification_allowed"] == 0
    assert naya["can_increase_independent_count"] == 0  # aggregator: never confirmation


def test_existing_registry_never_reseeded(db):
    SourcesRepo(db).create(name="مالک-منبع", platform="rss", url="u", status="APPROVED")
    n = seed_sources_if_empty(db, "config/source-seed.example.yml")
    assert n == 0
    assert [s["name"] for s in SourcesRepo(db).list()] == ["مالک-منبع"]


def test_watermark_survives_backup_restore_roundtrip(db, tmp_path):
    """Restore keeps checkpoints: post-restore fetch treats only newer content as new."""
    sid = SourcesRepo(db).create(name="w", platform="telegram", external_id="ch",
                                 status="APPROVED", source_type="telegram_web_preview",
                                 verification_allowed=False)
    SourcesRepo(db).mark_fetch(sid, True, fetch_state={"watermark": 92185, "etag": "x"})
    backup = str(tmp_path / "b.db")
    db.backup_to(backup)
    # simulate restore into a NEW db object
    from app.db.database import Database

    restored = Database(str(tmp_path / "restored.db"))
    import sqlite3

    src = sqlite3.connect(backup)
    with restored.tx() as conn:
        conn.executescript("\n".join(src.iterdump()))
    row = restored.query_one("SELECT fetch_state FROM sources WHERE id=?", (sid,))
    state = json.loads(row["fetch_state"])
    assert state["watermark"] == 92185  # checkpoint survived → archive stays archive
    restored.close()


def test_priority_and_flags_survive_roundtrip(db, tmp_path):
    sid = SourcesRepo(db).create(name="t1", platform="telegram", external_id="withyashar",
                                 status="APPROVED", priority=95, verification_allowed=False)
    SourcesRepo(db).db.execute("UPDATE sources SET breaking_source=1, polling_interval_min=1 WHERE id=?", (sid,))
    backup = str(tmp_path / "b2.db")
    db.backup_to(backup)
    from app.db.database import Database
    import sqlite3

    restored = Database(str(tmp_path / "r2.db"))
    src = sqlite3.connect(backup)
    with restored.tx() as conn:
        conn.executescript("\n".join(src.iterdump()))
    row = restored.query_one("SELECT priority, breaking_source, polling_interval_min,"
                             " verification_allowed FROM sources WHERE id=?", (sid,))
    assert (row["priority"], row["breaking_source"], row["polling_interval_min"],
            row["verification_allowed"]) == (95, 1, 1, 0)  # owner settings NOT reset
    restored.close()
