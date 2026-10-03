"""P3-D — bounded per-source context inheritance (REG-039, REG-031 context part).

Fixtures per PART-03 plan §18/§19 and the P3-D execution spec §11:
prefix + compatible next → inherit · TTL expiry → no inherit · new speaker →
reset · topic switch → reset · cross-source → never inherit · prefix alone →
0 claim/event/story/pub · restart-safe persistence · replay idempotency.
"""
import pytest

from app.db.database import Database
from app.db.migrate import apply_migrations
from app.db.repo import SourcesRepo
from app.newsroom.claim_completeness import evaluate as evaluate_completeness
from app.newsroom.source_context import (
    extract_explicit_speaker, is_prefix_item, load_live_context,
    resolve_context,
)
T0 = "2026-10-03T10:00:00"
TTL = 1800
PREFIX = "ترامپ به مجله تایم:"
QUOTE = "هیچ توافقی حاصل نشده است و مذاکرات به شکل جدی ادامه دارد"


def _source(db, name="s1"):
    return SourcesRepo(db).create(name=name, platform="telegram",
                                  url=f"t.me/{name}", status="APPROVED")


def _raw(db, source_id, key, text):
    cur = db.execute(
        "INSERT INTO raw_items(source_id, platform, external_key, text, fetched_at)"
        " VALUES(?,?,?,?,?)",
        (source_id, "telegram", key, text, T0))
    return int(cur.lastrowid)


def _ts(seconds: int) -> str:
    import datetime

    return (datetime.datetime.fromisoformat(T0)
            + datetime.timedelta(seconds=seconds)).isoformat()


# ---- required fixture: prefix + compatible next message → inherited context ----

def test_prefix_then_compatible_quote_inherits(db):
    sid = _source(db)
    resolve_context(db, source_id=sid, raw_item_id=None, text=PREFIX,
                    now=T0, ttl_seconds=TTL)
    d = resolve_context(db, source_id=sid, raw_item_id=None, text=QUOTE,
                        now=_ts(5), ttl_seconds=TTL)
    assert d.decision == "INHERIT" and d.inherited is not None
    assert d.inherited["speaker"] == "ترامپ به مجله تایم"
    assert d.inherited["event_type"] == "INTERVIEW"   # «مجله» hint


def test_self_attributed_same_speaker_inherits(db):
    """«ترامپ گفت …» inside a Trump/TIME interview window is the SAME speaker
    (containment) — context_ref inheritance is safe, never a reset."""
    sid = _source(db)
    resolve_context(db, source_id=sid, raw_item_id=None, text=PREFIX,
                    now=T0, ttl_seconds=TTL)
    d = resolve_context(db, source_id=sid, raw_item_id=None,
                        text="ترامپ گفت مذاکرات جدی است و ادامه دارد",
                        now=_ts(10), ttl_seconds=TTL)
    assert d.decision == "INHERIT"


# ---- required fixture: prefix + TTL expired → no inheritance ----

def test_ttl_expiry_no_inheritance(db):
    sid = _source(db)
    resolve_context(db, source_id=sid, raw_item_id=None, text=PREFIX,
                    now=T0, ttl_seconds=TTL)
    d = resolve_context(db, source_id=sid, raw_item_id=None, text=QUOTE,
                        now=_ts(TTL + 1), ttl_seconds=TTL)
    assert d.decision == "NO_CONTEXT"
    assert "NO_LIVE_CONTEXT" in d.reasons
    assert d.inherited is None


# ---- required fixture: prefix + new speaker → reset ----

def test_prefix_new_speaker_replaces_context(db):
    sid = _source(db)
    resolve_context(db, source_id=sid, raw_item_id=None, text=PREFIX,
                    now=T0, ttl_seconds=TTL)
    # a new speaker prefix is itself a colon-label prefix → newest context wins
    d = resolve_context(db, source_id=sid, raw_item_id=None, text="نتانیاهو:",
                        now=_ts(30), ttl_seconds=TTL)
    assert d.decision == "PREFIX_STORED"
    ctx = load_live_context(db, sid, now=_ts(31))
    assert ctx["speaker"] == "نتانیاهو"


def test_said_verb_new_speaker_resets(db):
    sid = _source(db)
    resolve_context(db, source_id=sid, raw_item_id=None, text=PREFIX,
                    now=T0, ttl_seconds=TTL)
    d = resolve_context(db, source_id=sid, raw_item_id=None,
                        text="نتانیاهو گفت جنگ تا نابودی حماس ادامه دارد",
                        now=_ts(30), ttl_seconds=TTL)
    assert d.decision == "RESET"
    assert "EXPLICIT_NEW_SPEAKER" in d.reasons
    assert load_live_context(db, sid, now=_ts(31)) is None  # context cleared


# ---- required fixture: prefix + topic switch → reset ----

def test_topic_switch_resets(db):
    sid = _source(db)
    resolve_context(db, source_id=sid, raw_item_id=None, text=PREFIX,
                    now=T0, ttl_seconds=TTL)
    d = resolve_context(db, source_id=sid, raw_item_id=None,
                        text="حمله موشکی به پایگاه آمریکایی در عراق رخ داد",
                        now=_ts(15), ttl_seconds=TTL)
    assert d.decision == "RESET"
    assert d.reasons[0] in ("HARD_CATEGORY_SWITCH", "CLEAR_TOPIC_CHANGE")
    assert load_live_context(db, sid, now=_ts(16)) is None


def test_event_boundary_marker_resets(db):
    sid = _source(db)
    resolve_context(db, source_id=sid, raw_item_id=None, text=PREFIX,
                    now=T0, ttl_seconds=TTL)
    d = resolve_context(db, source_id=sid, raw_item_id=None,
                        text="حمله دوم به پایگاه در عراق رخ داد و تلفات داشت",
                        now=_ts(20), ttl_seconds=TTL)
    assert d.decision == "RESET"
    assert "EVENT_BOUNDARY_MARKER" in d.reasons


# ---- required fixture: same context from different source → no inheritance ----

def test_cross_source_isolation(db):
    a = _source(db, "src_a")
    b = _source(db, "src_b")
    resolve_context(db, source_id=a, raw_item_id=None, text=PREFIX,
                    now=T0, ttl_seconds=TTL)
    d = resolve_context(db, source_id=b, raw_item_id=None, text=QUOTE,
                        now=_ts(5), ttl_seconds=TTL)
    assert d.decision == "NO_CONTEXT"       # never inherit globally
    # source A context untouched by B's activity
    assert load_live_context(db, a, now=_ts(6))["speaker"] == "ترامپ به مجله تایم"


# ---- required fixture: prefix alone → 0 claim/event/story/pub ----

def test_prefix_alone_produces_nothing(db):
    sid = _source(db)
    rid = _raw(db, sid, "k1", PREFIX)
    d = resolve_context(db, source_id=sid, raw_item_id=rid, text=PREFIX,
                        now=T0, ttl_seconds=TTL)
    assert d.decision == "PREFIX_STORED" and d.inherited is None
    for table in ("claims", "events", "stories", "publications"):
        n = db.query_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
        assert n == 0, f"{table} must stay empty"
    # and GATE-03 still classifies it unpublishable (REG-031 guarded)
    res = evaluate_completeness(PREFIX)
    assert res.state == "CONTEXT_ONLY" and res.publishable is False


def test_reg031_prefix_rules_unchanged():
    """REG-031 remains protected: fragments are CONTEXT_ONLY, never publishable."""
    for frag in ("ترامپ به مجله تایم:", "نتانیاهو:", "فوری:", "عاجل:",
                 "منابع عبری:", "در همین حال"):
        res = evaluate_completeness(frag)
        assert res.state == "CONTEXT_ONLY" and res.publishable is False


# ---- connective fragment: no context value, no destructive effect ----

def test_connective_fragment_preserves_context(db):
    sid = _source(db)
    resolve_context(db, source_id=sid, raw_item_id=None, text=PREFIX,
                    now=T0, ttl_seconds=TTL)
    d = resolve_context(db, source_id=sid, raw_item_id=None, text="در همین حال",
                        now=_ts(10), ttl_seconds=TTL)
    assert d.decision == "CONNECTIVE_FRAGMENT"
    assert load_live_context(db, sid, now=_ts(11))["speaker"] == "ترامپ به مجله تایم"


# ---- interview continuation (REG-029 alignment): minutes apart, within TTL ----

def test_interview_continuation_minutes_apart(db):
    sid = _source(db)
    resolve_context(db, source_id=sid, raw_item_id=None, text=PREFIX,
                    now=T0, ttl_seconds=TTL)
    for sec in (120, 600, 1200):
        d = resolve_context(db, source_id=sid, raw_item_id=None, text=QUOTE,
                            now=_ts(sec), ttl_seconds=TTL)
        assert d.decision == "INHERIT", f"continuation at +{sec}s lost"


# ---- required fixture: restart / context persistence → safe ----

def test_context_survives_restart(tmp_path):
    path = str(tmp_path / "ctx.db")
    db = Database(path)
    apply_migrations(db)
    sid = _source(db)
    resolve_context(db, source_id=sid, raw_item_id=None, text=PREFIX,
                    now=T0, ttl_seconds=TTL)
    db.close()
    db2 = Database(path)   # fresh process state, same DB file
    apply_migrations(db2)  # idempotent
    ctx = load_live_context(db2, sid, now=_ts(60))
    assert ctx is not None and ctx["speaker"] == "ترامپ به مجله تایم"
    d = resolve_context(db2, source_id=sid, raw_item_id=None, text=QUOTE,
                        now=_ts(61), ttl_seconds=TTL)
    assert d.decision == "INHERIT"
    db2.close()


# ---- required fixture: replay idempotency ----

def test_replay_idempotent_single_context_row(db):
    sid = _source(db)
    rid1 = _raw(db, sid, "k1", PREFIX)
    rid2 = _raw(db, sid, "k2", QUOTE)
    for _ in range(2):  # replay the same RawItems
        resolve_context(db, source_id=sid, raw_item_id=rid1, text=PREFIX,
                        now=T0, ttl_seconds=TTL)
        resolve_context(db, source_id=sid, raw_item_id=rid2, text=QUOTE,
                        now=_ts(5), ttl_seconds=TTL)
    rows = db.query("SELECT * FROM source_context")
    assert len(rows) == 1  # bounded: one live context per source, no dupes
    assert rows[0]["speaker"] == "ترامپ به مجله تایم"


# ---- deterministic speaker extraction unit checks ----

def test_extract_explicit_speaker_forms():
    # leading «label:» form IS an explicit speaker (P3-E interview turns)
    assert extract_explicit_speaker("نتانیاهو: جنگ ادامه دارد") == "نتانیاهو"
    assert extract_explicit_speaker("نتانیاهو گفت جنگ ادامه دارد") == "نتانیاهو"
    # connective turns are not speakers
    assert extract_explicit_speaker("در ادامه افزود: مذاکرات ادامه دارد") is None
    assert extract_explicit_speaker("هیچ توافقی حاصل نشده است") is None
    assert extract_explicit_speaker(PREFIX) == "ترامپ به مجله تایم"


def test_is_prefix_item_boundaries():
    assert is_prefix_item(PREFIX)
    assert is_prefix_item("فوری:")
    assert not is_prefix_item("نتانیاهو: جنگ تا نابودی حماس ادامه دارد و بیش از این نیز ادامه خواهد داشت")
    assert not is_prefix_item(QUOTE)
