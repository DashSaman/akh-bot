"""Backup/restore round-trip using the SQLite online backup API."""
import sqlite3


def test_backup_and_restore_roundtrip(db, tmp_path):
    from app.db.repo import SourcesRepo

    SourcesRepo(db).create(name="قبل از بکاپ", platform="rss", url="u", status="APPROVED")
    backup_path = str(tmp_path / "backup.db")
    db.backup_to(backup_path)

    # simulate writes continuing after backup
    SourcesRepo(db).create(name="بعد از بکاپ", platform="rss", url="u2", status="APPROVED")

    # restore: the backup must contain exactly the pre-backup state
    restored = sqlite3.connect(backup_path)
    names = [r[0] for r in restored.execute("SELECT name FROM sources").fetchall()]
    assert names == ["قبل از بکاپ"]
    restored.close()

    # source DB unaffected by the backup
    assert len(db.query("SELECT id FROM sources")) == 2
