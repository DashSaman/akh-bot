"""P3-D — burst aggregation (EVENT-003, REG-037).

Fixtures per the P3-D execution spec §8/§11: same-interview rapid fragments →
one group · rapid unrelated messages → separate groups · burst window is NOT
the continuation window · grouping is semantic, never time-only · replay
idempotency · one-group-per-item · restart-safe · cross-source isolation.
"""
import inspect

from app.db.repo import SourcesRepo
from app.newsroom import burst as burst_mod
from app.newsroom.burst import (
    assign_burst_group, group_items, make_signal, should_group,
)
from app.newsroom.event_fingerprint import (
    CONTINUATION_MINUTES, extract_fingerprint, hard_conflicts,
)

T0 = "2026-10-03T10:00:00"
WINDOW = 180  # EVENT_BURST_WINDOW_SECONDS default


def _source(db, name="s1"):
    return SourcesRepo(db).create(name=name, platform="telegram",
                                  url=f"t.me/{name}", status="APPROVED")


def _ts(seconds: int) -> str:
    import datetime

    return (datetime.datetime.fromisoformat(T0)
            + datetime.timedelta(seconds=seconds)).isoformat()


INTERVIEW_REF = "ترامپ به مجله تایم"


# ---- required fixture: same interview rapid fragments → one burst group ----

def test_same_interview_rapid_fragments_one_group(db):
    sid = _source(db)
    frags = [
        "هیچ توافقی حاصل نشده است و مذاکرات به شکل جدی ادامه دارد",
        "او گفت مذاکرات در حال حاضر ادامه دارد و متوقف نشده است",
        "تأکید کرد که توافق نهایی به شرایط وابسته است و هنوز قطعی نیست",
    ]
    ids = []
    for i, text in enumerate(frags):
        cur = db.execute(
            "INSERT INTO raw_items(source_id, platform, external_key, text,"
            " fetched_at) VALUES(?,?,?,?,?)",
            (sid, "telegram", f"m{i}", text, _ts(i * 30)))
        ids.append(int(cur.lastrowid))
    sigs = [(rid, make_signal(sid, text, _ts(i * 30), context_ref=INTERVIEW_REF))
            for i, (rid, text) in enumerate(zip(ids, frags))]
    result = group_items(db, sigs, window_seconds=WINDOW)
    assert len(set(result.values())) == 1          # all fragments, one group
    gid = next(iter(result.values()))
    row = db.query_one("SELECT * FROM burst_groups WHERE id=?", (gid,))
    assert row["raw_count"] == 3
    assert row["context_ref"] == INTERVIEW_REF
    members = db.query("SELECT raw_item_id FROM burst_members WHERE burst_group_id=?",
                       (gid,))
    assert {m["raw_item_id"] for m in members} == set(ids)


# ---- required fixture: rapid unrelated messages → separate burst groups ----

def test_rapid_unrelated_messages_separate_groups(db):
    sid = _source(db)
    items = [
        "حمله موشکی به پایگاه آمریکایی در عراق رخ داد",       # MILITARY_STRIKE
        "قیمت دلار در بازار آزاد امروز گران شد",               # MARKET_MOVE
        "قطعی اینترنت در سراسر کشور گزارش شد",                 # INTERNET_OUTAGE
    ]
    sigs = []
    for i, text in enumerate(items):
        rid = _insert(db, sid, f"u{i}", text, _ts(i * 20))
        sigs.append((rid, make_signal(sid, text, _ts(i * 20))))
    result = group_items(db, sigs, window_seconds=WINDOW)
    assert len(set(result.values())) == 3          # 20s apart, still separate
    types = {r["event_type"] for r in db.query("SELECT event_type FROM burst_groups")}
    assert types == {"MILITARY_STRIKE", "MARKET_MOVE", "INTERNET_OUTAGE"}


# ---- required fixture: burst window != continuation window (explicit) ----

def test_burst_window_is_not_continuation_window(db):
    sid = _source(db)
    text = "هیچ توافقی حاصل نشده است و مذاکرات به شکل جدی ادامه دارد"
    # burst layer: 10 minutes apart is FAR beyond the 180s burst window
    sig1 = make_signal(sid, text, T0, context_ref=INTERVIEW_REF)
    sig2 = make_signal(sid, text, _ts(600), context_ref=INTERVIEW_REF)
    ok, reasons = should_group(sig1, sig2, WINDOW)
    assert not ok and "WINDOW_EXCEEDED" in reasons
    # continuation layer: the same 10-minute pair is comfortably inside the
    # INTERVIEW continuation window (240 min) — no conflict, same event regime
    fp1 = extract_fingerprint(text, actor="ترامپ", occurred_at=T0)
    fp2 = extract_fingerprint(text, actor="ترامپ", occurred_at=_ts(600))
    assert "CONTINUATION_WINDOW_EXCEEDED" not in hard_conflicts(fp1, fp2, T0)
    # the two windows are distinct config domains, in different units
    assert CONTINUATION_MINUTES["INTERVIEW"] == 240          # minutes
    assert not [a for a in dir(burst_mod) if "CONTINUATION" in a]
    assert "CONTINUATION_MINUTES" not in inspect.getsource(burst_mod)
    assert CONTINUATION_MINUTES["INTERVIEW"] * 60 > WINDOW   # minutes ≠ seconds


# ---- REG-037 core: time proximity alone never groups ----

def test_time_proximity_alone_never_groups(db):
    sid = _source(db)
    a = make_signal(sid, "نشست بین‌المللی درباره آتش‌بس در دوحه آغاز شد", T0)
    b = make_signal(sid, "مصاحبه جدید وزیر امور خارجه منتشر شد", _ts(5))
    ok, reasons = should_group(a, b, WINDOW)
    assert not ok and "NO_SEMANTIC_LINK" in reasons  # 5s apart, still separate


# ---- boundary: rapid speaker switch → separate groups ----

def test_rapid_speaker_switch_separate_groups(db):
    sid = _source(db)
    a = make_signal(sid, "نتانیاهو گفت جلسه امنیتی برگزار شد و تصمیم گرفت", T0)
    b = make_signal(sid, "ترامپ گفت جلسه امنیتی برگزار شد و تصمیم گرفت", _ts(10))
    ok, reasons = should_group(a, b, WINDOW)
    assert not ok and "SPEAKER_SWITCH" in reasons
    rid_a = _insert(db, sid, "sp1", a.text, T0)
    rid_b = _insert(db, sid, "sp2", b.text, _ts(10))
    g1 = assign_burst_group(db, a, raw_item_id=rid_a, window_seconds=WINDOW)
    g2 = assign_burst_group(db, b, raw_item_id=rid_b, window_seconds=WINDOW)
    assert g1 != g2


# ---- cross-source isolation ----

def test_cross_source_never_grouped(db):
    a, b = _source(db, "src_a"), _source(db, "src_b")
    text = "هیچ توافقی حاصل نشده است و مذاکرات به شکل جدی ادامه دارد"
    ok, reasons = should_group(make_signal(a, text, T0),
                               make_signal(b, text, T0), WINDOW)
    assert not ok and "SOURCE_DIFFERS" in reasons


def _insert(db, sid, key, text, at):
    cur = db.execute(
        "INSERT INTO raw_items(source_id, platform, external_key, text,"
        " fetched_at) VALUES(?,?,?,?,?)", (sid, "telegram", key, text, at))
    return int(cur.lastrowid)


# ---- required fixture: replay idempotency ----

def test_replay_idempotent_no_duplicate_membership(db):
    sid = _source(db)
    texts = [
        "حمله موشکی به پایگاه آمریکایی در عراق رخ داد",
        "شلیک موشک به سمت پایگاه آمریکایی گزارش شد",
        "قیمت دلار در بازار آزاد امروز گران شد",
    ]
    plan = [(_insert(db, sid, f"r{i}", t, _ts(i * 15)),
             make_signal(sid, t, _ts(i * 15)))
            for i, t in enumerate(texts)]
    first = group_items(db, plan, window_seconds=WINDOW)
    second = group_items(db, plan, window_seconds=WINDOW)   # full replay
    assert first == second
    n_items = db.query_one("SELECT COUNT(*) AS n FROM burst_members")["n"]
    assert n_items == 3                                     # no dupes
    n_groups = db.query_one("SELECT COUNT(*) AS n FROM burst_groups")["n"]
    counts = {r["raw_count"] for r in db.query("SELECT raw_count FROM burst_groups")}
    assert n_groups == 2 and counts == {2, 1}               # strike pair + market


def test_item_assigned_to_exactly_one_group(db):
    """An item can never join two bursts — retry/reattach short-circuits."""
    sid = _source(db)
    rid1 = _insert(db, sid, "i1", "حمله موشکی به پایگاه آمریکایی در عراق رخ داد", T0)
    rid2 = _insert(db, sid, "i2", "شلیک موشک به سمت پایگاه آمریکایی گزارش شد", _ts(15))
    sig1 = make_signal(sid, "حمله موشکی به پایگاه آمریکایی در عراق رخ داد", T0)
    sig2 = make_signal(sid, "شلیک موشک به سمت پایگاه آمریکایی گزارش شد", _ts(15))
    g1 = assign_burst_group(db, sig1, raw_item_id=rid1, window_seconds=WINDOW)
    g2 = assign_burst_group(db, sig2, raw_item_id=rid2, window_seconds=WINDOW)
    assert g1 == g2                       # compatible pair → same group
    again = assign_burst_group(db, sig2, raw_item_id=rid2, window_seconds=WINDOW)
    assert again == g2                    # retry → same group, no second row
    rows = db.query("SELECT burst_group_id FROM burst_members WHERE raw_item_id=?", (rid2,))
    assert len(rows) == 1


# ---- required fixture: restart / persistence → safe ----

def test_groups_persist_across_restart(tmp_path):
    from app.db.database import Database
    from app.db.migrate import apply_migrations

    path = str(tmp_path / "burst.db")
    db = Database(path)
    apply_migrations(db)
    sid = _source(db)
    rid1 = _insert(db, sid, "r1", "حمله موشکی به پایگاه آمریکایی در عراق رخ داد", T0)
    sig1 = make_signal(sid, "حمله موشکی به پایگاه آمریکایی در عراق رخ داد", T0)
    g1 = assign_burst_group(db, sig1, raw_item_id=rid1, window_seconds=WINDOW)
    db.close()

    db2 = Database(path)
    apply_migrations(db2)
    rid2 = _insert(db2, sid, "r2", "شلیک موشک به سمت پایگاه آمریکایی گزارش شد", _ts(60))
    sig2 = make_signal(sid, "شلیک موشک به سمت پایگاه آمریکایی گزارش شد", _ts(60))
    g2 = assign_burst_group(db2, sig2, raw_item_id=rid2, window_seconds=WINDOW)
    assert g2 == g1                        # post-restart item joins pre-restart group
    assert db2.query_one("SELECT raw_count FROM burst_groups WHERE id=?", (g1,))["raw_count"] == 2
    db2.close()


# ---- deterministic ordering ----

def test_grouping_order_deterministic(db):
    sid = _source(db)
    texts = ["حمله موشکی به پایگاه آمریکایی در عراق رخ داد",
             "شلیک موشک به سمت پایگاه آمریکایی گزارش شد",
             "قیمت دلار در بازار آزاد امروز گران شد"]
    rids = [_insert(db, sid, f"d{i}", t, _ts(i * 15)) for i, t in enumerate(texts)]
    plan_fwd = [(rids[i], make_signal(sid, t, _ts(i * 15)))
                for i, t in enumerate(texts)]
    groups_fwd = group_items(db, plan_fwd, window_seconds=WINDOW)
    # replay in reverse arrival order must land every item in the same group
    plan_rev = [(rids[i], make_signal(sid, t, _ts(i * 15)))
                for i, t in reversed(list(enumerate(texts)))]
    groups_rev = group_items(db, plan_rev, window_seconds=WINDOW)
    assert groups_fwd == groups_rev


# ---- P3-D scope guard: no publication side effects ----

def test_burst_has_no_publication_side_effects(db):
    sid = _source(db)
    rid = _insert(db, sid, "x1", "حمله موشکی به پایگاه آمریکایی در عراق رخ داد", T0)
    sig = make_signal(sid, "حمله موشکی به پایگاه آمریکایی در عراق رخ داد", T0)
    assign_burst_group(db, sig, raw_item_id=rid, window_seconds=WINDOW)
    for table in ("publications", "jobs", "stories", "story_versions"):
        n = db.query_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
        assert n == 0, f"{table} must stay untouched (P3-E owns publication)"


# ---- fail-closed time handling ----

def test_unparseable_time_never_groups(db):
    sid = _source(db)
    a = make_signal(sid, "حمله موشکی به پایگاه آمریکایی در عراق رخ داد", T0)
    b = make_signal(sid, "شلیک موشک به سمت پایگاه آمریکایی گزارش شد", "garbage")
    ok, reasons = should_group(a, b, WINDOW)
    assert not ok and "TIME_UNPARSEABLE" in reasons
