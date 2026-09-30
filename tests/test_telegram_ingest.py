"""Telegram ingestion helpers: revision immutability + backfill protection."""
from app.db.repo import SourcesRepo
from app.ingestion.telegram_ingest import apply_message_snapshot


def _source(db):
    return SourcesRepo(db).create(name="ch", platform="telegram", external_id="@ch",
                                  status="APPROVED")


def test_new_message_stored_and_duplicate_detected(db):
    sid = _source(db)
    src = SourcesRepo(db).get(sid)
    msg = {"chat_id": -100123, "message_id": 5, "text": "پیام آزمونی شماره یک",
           "date": "2030-01-01T00:00:00+00:00", "edit_date": None, "forward_from": None}
    assert apply_message_snapshot(db, src, msg) == "stored"
    assert apply_message_snapshot(db, src, msg) == "duplicate"
    assert len(db.query("SELECT id FROM raw_items")) == 1


def test_edited_message_creates_new_revision_never_overwrites(db):
    sid = _source(db)
    src = SourcesRepo(db).get(sid)
    msg = {"chat_id": -100123, "message_id": 7, "text": "متن اولیه گزارش",
           "date": "2030-01-01T00:00:00+00:00", "edit_date": None, "forward_from": None}
    apply_message_snapshot(db, src, msg)
    msg2 = dict(msg, text="متن اولیه گزارش - اصلاح شد", edit_date="2030-01-01T01:00:00+00:00")
    assert apply_message_snapshot(db, src, msg2) == "revised"
    revs = db.query("SELECT rev_no, text FROM item_revisions ORDER BY rev_no")
    assert revs[0]["text"] == "متن اولیه گزارش"          # original preserved
    assert revs[1]["text"].endswith("اصلاح شد")           # new version appended
    row = db.query_one("SELECT text FROM raw_items WHERE id=(SELECT MIN(id) FROM raw_items)")
    assert row["text"].endswith("اصلاح شد")               # current = latest, history intact


def test_prewritten_archive_is_store_only(db):
    """Messages older than source activation are stored but never publish-eligible."""
    sid = _source(db)
    src = SourcesRepo(db).get(sid)
    old = {"chat_id": -100123, "message_id": 1, "text": "پیام بسیار قدیمی از آرشیو",
           "date": "2020-01-01T00:00:00+00:00", "edit_date": None, "forward_from": None}
    assert apply_message_snapshot(db, src, old) == "stored"
    item = db.query_one("SELECT activation_ok FROM raw_items")
    assert item["activation_ok"] == 0  # STORE_ONLY


def test_forwarded_message_lineage(db):
    sid = _source(db)
    src = SourcesRepo(db).get(sid)
    fwd = {"chat_id": -100123, "message_id": 9, "text": "بازنشر گزارش رویترز از حمله",
           "date": "2030-01-01T00:00:00+00:00", "edit_date": None, "forward_from": -100999}
    apply_message_snapshot(db, src, fwd)
    item = db.query_one("SELECT lineage_key, forward_from FROM raw_items")
    assert item["lineage_key"] == "tg:-100999"  # copy chains collapse to origin
